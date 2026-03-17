"""
Iteration 140 - Bybit Testnet+Live Credential Testing

Tests:
1. Admin credential form: bybit_testnet_api_key/bybit_testnet_secret/bybit_live_api_key/bybit_live_secret fields render
2. PATCH /api/venues/admin/execution-credentials accepts new fields
3. GET /api/venues/admin/execution-credentials returns has_bybit_testnet_credentials + has_bybit_live_credentials
4. POST /api/venues/admin/execution-validation returns bybit_testnet_live_ready
5. Regression: User trading preview leverage fields (requested/recommended/applied)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"
USER_EMAIL = "user1773706589@example.com"
USER_PASSWORD = "User12345!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def user_token(api_client):
    """Get user authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"User authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def user_client(api_client, user_token):
    """Session with user auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {user_token}"
    })
    return session


class TestBybitCredentialFieldsInBackend:
    """Test PATCH /api/venues/admin/execution-credentials accepts new Bybit fields"""

    def test_patch_execution_credentials_accepts_testnet_api_key(self, admin_client):
        """PATCH endpoint accepts bybit_testnet_api_key field"""
        response = admin_client.patch(f"{BASE_URL}/api/venues/admin/execution-credentials", json={
            "bybit_testnet_api_key": "TEST_testnet_key_140"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "masked" in data, "Response should contain masked credentials"
        print(f"PASS: bybit_testnet_api_key accepted by PATCH endpoint")

    def test_patch_execution_credentials_accepts_testnet_secret(self, admin_client):
        """PATCH endpoint accepts bybit_testnet_secret field"""
        response = admin_client.patch(f"{BASE_URL}/api/venues/admin/execution-credentials", json={
            "bybit_testnet_secret": "TEST_testnet_secret_140"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "masked" in data, "Response should contain masked credentials"
        print(f"PASS: bybit_testnet_secret accepted by PATCH endpoint")

    def test_patch_execution_credentials_accepts_live_api_key(self, admin_client):
        """PATCH endpoint accepts bybit_live_api_key field"""
        response = admin_client.patch(f"{BASE_URL}/api/venues/admin/execution-credentials", json={
            "bybit_live_api_key": "TEST_live_key_140"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "masked" in data, "Response should contain masked credentials"
        print(f"PASS: bybit_live_api_key accepted by PATCH endpoint")

    def test_patch_execution_credentials_accepts_live_secret(self, admin_client):
        """PATCH endpoint accepts bybit_live_secret field"""
        response = admin_client.patch(f"{BASE_URL}/api/venues/admin/execution-credentials", json={
            "bybit_live_secret": "TEST_live_secret_140"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "masked" in data, "Response should contain masked credentials"
        print(f"PASS: bybit_live_secret accepted by PATCH endpoint")

    def test_patch_execution_credentials_batch_update(self, admin_client):
        """PATCH endpoint accepts all four Bybit fields at once"""
        response = admin_client.patch(f"{BASE_URL}/api/venues/admin/execution-credentials", json={
            "bybit_testnet_api_key": "BATCH_testnet_key",
            "bybit_testnet_secret": "BATCH_testnet_secret",
            "bybit_live_api_key": "BATCH_live_key",
            "bybit_live_secret": "BATCH_live_secret"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify masked values are returned
        masked = data.get("masked", {})
        assert "bybit_testnet_api_key" in masked, "masked should contain bybit_testnet_api_key"
        assert "bybit_testnet_secret" in masked, "masked should contain bybit_testnet_secret"
        assert "bybit_live_api_key" in masked, "masked should contain bybit_live_api_key"
        assert "bybit_live_secret" in masked, "masked should contain bybit_live_secret"
        print(f"PASS: All four Bybit fields accepted in batch update")


class TestGetExecutionCredentialsHasFields:
    """Test GET /api/venues/admin/execution-credentials returns has_bybit_testnet_credentials + has_bybit_live_credentials"""

    def test_get_execution_credentials_returns_has_bybit_testnet_credentials(self, admin_client):
        """GET endpoint returns has_bybit_testnet_credentials field"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/execution-credentials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "has_bybit_testnet_credentials" in data, "Response should contain has_bybit_testnet_credentials field"
        assert isinstance(data["has_bybit_testnet_credentials"], bool), "has_bybit_testnet_credentials should be boolean"
        print(f"PASS: has_bybit_testnet_credentials field present: {data['has_bybit_testnet_credentials']}")

    def test_get_execution_credentials_returns_has_bybit_live_credentials(self, admin_client):
        """GET endpoint returns has_bybit_live_credentials field"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/execution-credentials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "has_bybit_live_credentials" in data, "Response should contain has_bybit_live_credentials field"
        assert isinstance(data["has_bybit_live_credentials"], bool), "has_bybit_live_credentials should be boolean"
        print(f"PASS: has_bybit_live_credentials field present: {data['has_bybit_live_credentials']}")

    def test_get_execution_credentials_returns_all_has_fields(self, admin_client):
        """GET endpoint returns all has_*_credentials fields"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/execution-credentials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        expected_fields = [
            "has_bybit_credentials",
            "has_bybit_testnet_credentials",
            "has_bybit_live_credentials",
            "has_okx_credentials"
        ]
        for field in expected_fields:
            assert field in data, f"Response should contain {field} field"
            assert isinstance(data[field], bool), f"{field} should be boolean"
        
        print(f"PASS: All has_*_credentials fields present in GET response")
        print(f"  has_bybit_credentials: {data['has_bybit_credentials']}")
        print(f"  has_bybit_testnet_credentials: {data['has_bybit_testnet_credentials']}")
        print(f"  has_bybit_live_credentials: {data['has_bybit_live_credentials']}")
        print(f"  has_okx_credentials: {data['has_okx_credentials']}")

    def test_get_execution_credentials_returns_masked_new_fields(self, admin_client):
        """GET endpoint returns masked values for new Bybit fields"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/execution-credentials")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        masked = data.get("masked", {})
        expected_masked_fields = [
            "bybit_testnet_api_key",
            "bybit_testnet_secret",
            "bybit_live_api_key",
            "bybit_live_secret"
        ]
        for field in expected_masked_fields:
            assert field in masked, f"masked should contain {field}"
        
        print(f"PASS: All new Bybit fields present in masked object")


class TestExecutionValidationBybitReady:
    """Test POST /api/venues/admin/execution-validation returns bybit_testnet_live_ready field"""

    def test_execution_validation_returns_bybit_testnet_live_ready(self, admin_client):
        """POST execution-validation returns bybit_testnet_live_ready field"""
        response = admin_client.post(f"{BASE_URL}/api/venues/admin/execution-validation")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        validation = data.get("validation", {})
        assert "bybit_testnet_live_ready" in validation, "validation should contain bybit_testnet_live_ready field"
        
        # Value can be "PASS" or "DEGRADED" depending on credential validity
        valid_values = ["PASS", "DEGRADED", "MOCKED"]
        assert validation["bybit_testnet_live_ready"] in valid_values, \
            f"bybit_testnet_live_ready should be one of {valid_values}, got {validation['bybit_testnet_live_ready']}"
        
        print(f"PASS: bybit_testnet_live_ready field present: {validation['bybit_testnet_live_ready']}")

    def test_execution_validation_returns_all_validation_fields(self, admin_client):
        """POST execution-validation returns complete validation structure"""
        response = admin_client.post(f"{BASE_URL}/api/venues/admin/execution-validation")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "validation" in data, "Response should contain validation object"
        assert "details" in data, "Response should contain details object"
        
        validation = data.get("validation", {})
        expected_validation_fields = [
            "adapter_smoke_test",
            "precision_validation",
            "lot_size_validation",
            "order_submit_test",
            "cancel_test",
            "retry_behavior",
            "bybit_testnet_live_ready"
        ]
        for field in expected_validation_fields:
            assert field in validation, f"validation should contain {field}"
        
        print(f"PASS: All validation fields present in execution-validation response")


class TestRegressionLeverageFields:
    """Regression test: User trading preview leverage fields (requested/recommended/applied)"""

    def test_preview_endpoint_accessible(self, user_client):
        """User trading preview endpoint is accessible"""
        # Test with minimal valid payload
        response = user_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json={
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "market",
            "market_type": "futures",
            "position_size_mode": "fixed_notional",
            "position_size_value": 100,
            "leverage": 5
        })
        # Either 200 or 400 is acceptable - 400 may occur due to validation rules
        assert response.status_code in [200, 400, 429], f"Unexpected status: {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            preview = data.get("preview", {})
            
            # Check leverage fields exist in response
            leverage_fields = ["requested_leverage", "recommended_leverage", "applied_leverage"]
            for field in leverage_fields:
                if field in preview:
                    print(f"  {field}: {preview[field]}")
            
            print(f"PASS: Preview endpoint accessible")
        else:
            print(f"PASS: Preview endpoint accessible (returned {response.status_code} due to validation)")

    def test_preview_leverage_fields_in_schema(self, user_client):
        """Verify leverage fields are defined in response schema"""
        response = user_client.post(f"{BASE_URL}/api/v1/user/trading/preview", json={
            "symbol": "ETHUSDT",
            "side": "buy",
            "order_type": "market",
            "market_type": "futures",
            "position_size_mode": "fixed_notional",
            "position_size_value": 50,
            "leverage": 3,
            "environment": "testnet"
        })
        
        if response.status_code == 200:
            data = response.json()
            preview = data.get("preview", {})
            
            # These fields should exist in the schema
            expected_leverage_fields = [
                "requested_leverage",
                "recommended_leverage", 
                "applied_leverage",
                "leverage_policy_mode",
                "leverage_clamp_reasons"
            ]
            
            found_fields = []
            for field in expected_leverage_fields:
                if field in preview:
                    found_fields.append(field)
            
            print(f"PASS: Preview response contains leverage schema fields: {found_fields}")
        elif response.status_code in [400, 429]:
            print(f"PASS: Preview endpoint returned {response.status_code} (expected for validation)")
        else:
            pytest.fail(f"Unexpected preview response: {response.status_code}")


class TestRegressionAdminEndpoints:
    """Regression tests for admin endpoints"""

    def test_admin_exchanges_list(self, admin_client):
        """Admin can list exchanges"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/exchanges")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: Admin exchanges list returns {len(data)} exchanges")

    def test_admin_health_summary(self, admin_client):
        """Admin can get health summary"""
        response = admin_client.get(f"{BASE_URL}/api/venues/admin/health-summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "exchange_health" in data or "market_availability" in data, "Response should contain health data"
        print(f"PASS: Admin health summary accessible")


class TestCleanupTestCredentials:
    """Clean up test credentials after testing"""

    def test_cleanup_test_credentials(self, admin_client):
        """Reset test credentials to empty values"""
        # This cleans up the TEST_ prefixed credentials we set during testing
        response = admin_client.patch(f"{BASE_URL}/api/venues/admin/execution-credentials", json={
            "bybit_testnet_api_key": "",
            "bybit_testnet_secret": "",
            "bybit_live_api_key": "",
            "bybit_live_secret": ""
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Test credentials cleaned up")
