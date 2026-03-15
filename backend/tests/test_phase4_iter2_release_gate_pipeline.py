"""
Phase-4 Iteration-2 Continuation: Release Gate Automation Pipeline Tests
Tests for:
  - Monitoring endpoint: release_gate_status and release_gate_last_checked fields
  - Admin release gate: BLOCKED status with live_activation=disabled
  - Test order blocked with invalid key (400 status, not 500)
  - Execution quality response: strategy_type/volatility_regime/volatility_pct fields
  - User exchange settings flow (GET/PUT, no plaintext)
  - Permission status controls format (can_trade/can_futures/timestamp_sync/rate_limit_ok)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL env var required"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_token_and_id():
    """Create a test user and get token or use existing test user"""
    test_email = "TEST_phase4iter2_pipeline@example.com"
    test_password = "TestPassword123!"
    
    # Try login first
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": test_email, "password": test_password},
    )
    
    if login_resp.status_code == 200:
        data = login_resp.json()
        return data["access_token"], data["user"]["id"]
    
    # If not found, register and approve the user
    admin_resp = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", ""), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
    )
    admin_token = admin_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    # Register user
    reg_resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": test_email, "password": test_password},
    )
    if reg_resp.status_code not in [201, 200, 400]:
        pytest.skip(f"Could not create test user: {reg_resp.text}")
    
    # Get pending users and approve
    pending_resp = requests.get(
        f"{BASE_URL}/api/auth/admin/user-approval-requests?status=pending",
        headers=admin_headers,
    )
    if pending_resp.status_code == 200:
        for user in pending_resp.json():
            if user["email"] == test_email:
                requests.post(
                    f"{BASE_URL}/api/auth/admin/user-approval-requests/{user['id']}/approve",
                    headers=admin_headers,
                )
                break
    
    # Now login
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": test_email, "password": test_password},
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Could not login test user: {login_resp.text}")
    
    data = login_resp.json()
    return data["access_token"], data["user"]["id"]


@pytest.fixture
def user_headers(user_token_and_id):
    token, _ = user_token_and_id
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestMonitoringReleaseGateFields:
    """GET /api/pipeline/monitoring - Monitoring endpoint release gate fields"""

    def test_monitoring_returns_200(self, admin_headers):
        """GET monitoring should return 200"""
        response = requests.get(f"{BASE_URL}/api/pipeline/monitoring", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_monitoring_has_release_gate_status(self, admin_headers):
        """GET monitoring should have release_gate_status field"""
        response = requests.get(f"{BASE_URL}/api/pipeline/monitoring", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "release_gate_status" in data, "Monitoring should have release_gate_status field"
        # Valid values: PASS, WARNING, BLOCKED, UNKNOWN
        assert data["release_gate_status"] in ["PASS", "WARNING", "BLOCKED", "UNKNOWN", "-"], \
            f"release_gate_status should be valid, got: {data['release_gate_status']}"

    def test_monitoring_has_release_gate_last_checked(self, admin_headers):
        """GET monitoring should have release_gate_last_checked field"""
        response = requests.get(f"{BASE_URL}/api/pipeline/monitoring", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "release_gate_last_checked" in data, "Monitoring should have release_gate_last_checked field"
        # Can be ISO timestamp string or "-"
        assert isinstance(data["release_gate_last_checked"], str), \
            "release_gate_last_checked should be a string"


class TestAdminReleaseGateBlockedBehavior:
    """GET /api/phase4/admin/release-gate - Release gate BLOCKED => live_activation=disabled"""

    def test_release_gate_returns_200(self, admin_headers):
        """GET release-gate should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/release-gate", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_release_gate_blocked_has_disabled_live_activation(self, admin_headers):
        """When release gate is BLOCKED, live_activation should be 'disabled'"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/release-gate", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "status" in data, "Must have status field"
        assert "live_activation" in data, "Must have live_activation field"
        assert "reasons" in data, "Must have reasons field"
        
        # If status is BLOCKED, live_activation must be disabled
        if data["status"] == "BLOCKED":
            assert data["live_activation"] == "disabled", \
                f"When status=BLOCKED, live_activation should be 'disabled', got: {data['live_activation']}"
        else:
            # If not blocked, live_activation should be guarded or enabled
            assert data["live_activation"] in ["guarded", "enabled", "disabled"], \
                f"live_activation should be valid, got: {data['live_activation']}"

    def test_release_gate_has_reasons_list(self, admin_headers):
        """GET release-gate should have reasons list"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/release-gate", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data["reasons"], list), "reasons should be a list"


class TestTestOrderInvalidKeyBlocking:
    """POST /api/phase4/test-order - Test order blocked with invalid key returns 400"""

    def test_test_order_setup_invalid_key(self, user_headers):
        """Setup: Save invalid API credentials for test user"""
        payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "INVALID_FAKE_KEY_FOR_TESTING_12345",
            "api_secret": "INVALID_FAKE_SECRET_FOR_TESTING_67890",
        }
        response = requests.put(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=user_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_test_order_blocked_returns_400_not_500(self, user_headers):
        """POST test-order with invalid key should return 400, NOT 500"""
        response = requests.post(f"{BASE_URL}/api/phase4/test-order", headers=user_headers)
        
        # Critical: Should NOT be 500 - that would be unhandled error
        assert response.status_code != 500, \
            f"Test order should NOT return 500 server error, got: {response.status_code}: {response.text}"
        
        # Should be 400 (bad request - permission check failed)
        assert response.status_code == 400, \
            f"Test order with invalid key should return 400, got: {response.status_code}"
        
        # Check error has detail message
        data = response.json()
        assert "detail" in data, "Error response should have detail field"

    def test_test_order_error_message_meaningful(self, user_headers):
        """POST test-order error message should be meaningful"""
        response = requests.post(f"{BASE_URL}/api/phase4/test-order", headers=user_headers)
        
        if response.status_code == 400:
            data = response.json()
            detail = data.get("detail", "")
            # Should mention permission check or similar
            assert len(detail) > 5, f"Error detail should be meaningful, got: {detail}"


class TestExecutionQualityResponseModel:
    """GET /api/phase4/admin/execution-quality - Execution quality response model fields"""

    def test_execution_quality_list_returns_200(self, admin_headers):
        """GET admin execution-quality should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_execution_quality_is_list(self, admin_headers):
        """GET admin execution-quality should return a list"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_execution_quality_items_have_strategy_volatility_fields(self, admin_headers):
        """Execution quality items should have strategy_type/volatility_regime/volatility_pct fields"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # If there are any items, check the fields
        if len(data) > 0:
            item = data[0]
            
            # Check required fields
            assert "strategy_type" in item, "Item should have strategy_type field"
            assert "volatility_regime" in item, "Item should have volatility_regime field"
            assert "volatility_pct" in item, "Item should have volatility_pct field"
            
            # Check execution quality fields
            assert "execution_id" in item
            assert "symbol" in item
            assert "status" in item
            assert "expected_price" in item
            assert "execution_quality_score" in item
            
            # Validate volatility_regime values
            assert item["volatility_regime"] in ["low", "medium", "high", "unknown"], \
                f"volatility_regime should be valid, got: {item['volatility_regime']}"
            
            # volatility_pct should be a number
            assert isinstance(item["volatility_pct"], (int, float)), \
                f"volatility_pct should be a number, got: {type(item['volatility_pct'])}"


class TestUserExchangeSettingsFlow:
    """GET/PUT /api/phase4/exchange-settings - User exchange settings (no plaintext)"""

    def test_get_exchange_settings_returns_200(self, user_headers):
        """GET exchange-settings should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_get_exchange_settings_no_plaintext_credentials(self, user_headers):
        """GET exchange-settings should NOT return plaintext credentials"""
        response = requests.get(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Must have boolean flags
        assert "has_api_key" in data
        assert "has_api_secret" in data
        
        # Must NOT have plaintext
        assert "api_key" not in data or data.get("api_key") is None
        assert "api_secret" not in data or data.get("api_secret") is None
        assert "api_key_encrypted" not in data
        assert "api_secret_encrypted" not in data

    def test_put_exchange_settings_updates_correctly(self, user_headers):
        """PUT exchange-settings should update and return updated flags"""
        payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "TEST_NEW_KEY_12345",
            "api_secret": "TEST_NEW_SECRET_67890",
        }
        response = requests.put(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=user_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["has_api_key"] is True
        assert data["has_api_secret"] is True
        assert data["exchange"] == "binance"
        assert data["mode"] == "testnet"


class TestPermissionStatusControlsFormat:
    """GET /api/phase4/permission-status - Permission controls format"""

    def test_permission_status_returns_200(self, user_headers):
        """GET permission-status should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status", headers=user_headers)
        assert response.status_code == 200

    def test_permission_status_has_required_controls(self, user_headers):
        """Permission status should have can_trade/can_futures/timestamp_sync/rate_limit_ok"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "controls" in data
        controls = data["controls"]
        control_keys = [c["key"] for c in controls]
        
        # Required control keys
        assert "can_trade" in control_keys, "Must have can_trade control"
        assert "can_futures" in control_keys, "Must have can_futures control"
        assert "timestamp_sync" in control_keys, "Must have timestamp_sync control"
        assert "rate_limit_ok" in control_keys, "Must have rate_limit_ok control"

    def test_permission_status_controls_have_required_fields(self, user_headers):
        """Each permission control should have key/status/reason/timestamp"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        for control in data["controls"]:
            assert "key" in control, "Control must have key"
            assert "status" in control, "Control must have status"
            assert "reason" in control, "Control must have reason"
            assert "timestamp" in control, "Control must have timestamp"
            
            # Status should be pass or fail
            assert control["status"] in ["pass", "fail"], \
                f"Control status should be pass or fail, got: {control['status']}"


class TestAdminLiveReadinessScore:
    """GET /api/phase4/admin/live-readiness-score - Live readiness score"""

    def test_live_readiness_score_returns_200(self, admin_headers):
        """GET live-readiness-score should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/live-readiness-score", headers=admin_headers)
        assert response.status_code == 200

    def test_live_readiness_score_has_all_fields(self, admin_headers):
        """Live readiness score should have all required fields"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/live-readiness-score", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "readiness_score",
            "permission_ready",
            "risk_engine_pass",
            "execution_simulation_pass",
            "correlation_model_pass",
            "hardening_checklist_pass",
            "release_gate_status",
            "live_activation",
            "critical_blockers",
        ]
        
        for field in required_fields:
            assert field in data, f"Must have {field} field"

    def test_live_readiness_blocked_means_disabled_live(self, admin_headers):
        """When release_gate_status=BLOCKED, live_activation should be disabled"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/live-readiness-score", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        if data["release_gate_status"] == "BLOCKED":
            assert data["live_activation"] == "disabled", \
                f"When BLOCKED, live_activation should be disabled, got: {data['live_activation']}"


class TestLatestExecutionQuality:
    """GET /api/phase4/execution-quality/latest - User's latest execution quality"""

    def test_latest_execution_quality_endpoint_exists(self, user_headers):
        """GET execution-quality/latest should return 200 or 404 (no records)"""
        response = requests.get(f"{BASE_URL}/api/phase4/execution-quality/latest", headers=user_headers)
        # 200 if there are records, 404 if no records yet
        assert response.status_code in [200, 404], \
            f"Expected 200 or 404, got {response.status_code}: {response.text}"

    def test_latest_execution_quality_has_fields_if_exists(self, user_headers):
        """If latest execution quality exists, it should have strategy/volatility fields"""
        response = requests.get(f"{BASE_URL}/api/phase4/execution-quality/latest", headers=user_headers)
        
        if response.status_code == 200:
            data = response.json()
            
            assert "strategy_type" in data, "Must have strategy_type"
            assert "volatility_regime" in data, "Must have volatility_regime"
            assert "volatility_pct" in data, "Must have volatility_pct"
            assert "execution_quality_score" in data, "Must have execution_quality_score"
