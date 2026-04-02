"""
Phase-4 Iteration-2: Exchange Settings, Permission Status, Test Order, Admin Endpoints
Tests for:
  - User exchange settings API (GET/PUT /api/phase4/exchange-settings)
  - Permission status (GET /api/phase4/permission-status)
  - Admin permission status (GET /api/phase4/admin/permission-status)
  - Admin live readiness score (GET /api/phase4/admin/live-readiness-score)
  - Admin release gate (GET /api/phase4/admin/release-gate)
  - Test order blocking for invalid credentials (POST /api/phase4/test-order)
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
    # First try to login as existing test user
    test_email = "TEST_phase4iter2@example.com"
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
    # Need admin token first
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
    if reg_resp.status_code not in [201, 200, 400]:  # 400 might mean user exists
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


class TestUserExchangeSettings:
    """GET/PUT /api/phase4/exchange-settings - User exchange settings"""

    def test_get_exchange_settings_returns_200(self, user_headers):
        """GET exchange-settings should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_get_exchange_settings_no_plaintext(self, user_headers):
        """GET exchange-settings should return has_api_key/has_api_secret flags, NOT plaintext"""
        response = requests.get(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Must have these boolean flags
        assert "has_api_key" in data, "Response must contain has_api_key field"
        assert "has_api_secret" in data, "Response must contain has_api_secret field"
        
        # Must NOT return plaintext credentials
        assert "api_key" not in data or data.get("api_key") is None, "Should NOT return plaintext api_key"
        assert "api_secret" not in data or data.get("api_secret") is None, "Should NOT return plaintext api_secret"
        assert "api_key_encrypted" not in data, "Should NOT return encrypted key in response"
        assert "api_secret_encrypted" not in data, "Should NOT return encrypted secret in response"
        
        # Check expected structure
        assert "exchange" in data
        assert "mode" in data
        assert "updated_at" in data

    def test_put_exchange_settings_saves_credentials(self, user_headers):
        """PUT exchange-settings should save credentials (encrypted)"""
        payload = {
            "exchange": "binance",
            "mode": "live",
            "api_key": "fake_test_api_key_12345",
            "api_secret": "fake_test_api_secret_67890",
        }
        response = requests.put(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=user_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # After save, should indicate keys are present
        assert data["has_api_key"] is True, "has_api_key should be True after save"
        assert data["has_api_secret"] is True, "has_api_secret should be True after save"
        assert data["exchange"] == "binance"
        assert data["mode"] == "live"

    def test_put_exchange_settings_requires_auth(self):
        """PUT exchange-settings should require authentication"""
        payload = {
            "exchange": "binance",
            "mode": "live",
            "api_key": "test",
            "api_secret": "test",
        }
        response = requests.put(f"{BASE_URL}/api/phase4/exchange-settings", json=payload)
        assert response.status_code == 401


class TestUserPermissionStatus:
    """GET /api/phase4/permission-status - User permission status"""

    def test_permission_status_returns_200(self, user_headers):
        """GET permission-status should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status", headers=user_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_permission_status_response_format(self, user_headers):
        """GET permission-status should return proper format with controls"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "overall_status" in data, "Must have overall_status field"
        assert "live_activation" in data, "Must have live_activation field"
        assert "controls" in data, "Must have controls list"
        
        # Validate controls structure
        controls = data["controls"]
        assert isinstance(controls, list), "controls should be a list"
        
        # Check expected control keys
        control_keys = [c["key"] for c in controls]
        assert "can_trade" in control_keys, "controls should have can_trade"
        assert "can_futures" in control_keys, "controls should have can_futures"
        assert "timestamp_sync" in control_keys, "controls should have timestamp_sync"
        assert "rate_limit_ok" in control_keys, "controls should have rate_limit_ok"
        
        # Check control structure
        for control in controls:
            assert "key" in control
            assert "status" in control
            assert "reason" in control
            assert "timestamp" in control

    def test_permission_status_fails_with_invalid_credentials(self, user_headers):
        """Permission status should show fail when credentials are invalid/fake"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        # With fake credentials, should not be pass
        assert data["overall_status"] in ["fail", "blocked"], f"Expected fail status with fake credentials, got: {data['overall_status']}"

    def test_permission_status_requires_auth(self):
        """GET permission-status should require authentication"""
        response = requests.get(f"{BASE_URL}/api/phase4/permission-status")
        assert response.status_code == 401


class TestAdminPermissionStatus:
    """GET /api/phase4/admin/permission-status - Admin permission overview"""

    def test_admin_permission_status_returns_200(self, admin_headers):
        """GET admin permission-status should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/permission-status", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_admin_permission_status_response_format(self, admin_headers):
        """GET admin permission-status should return proper format"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/permission-status", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields same as user permission status
        assert "overall_status" in data
        assert "live_activation" in data
        assert "controls" in data
        
        # Controls should have expected keys
        if data["controls"]:
            control_keys = [c["key"] for c in data["controls"]]
            assert "can_trade" in control_keys
            assert "can_futures" in control_keys
            assert "timestamp_sync" in control_keys
            assert "rate_limit_ok" in control_keys

    def test_admin_permission_status_requires_admin(self, user_headers):
        """GET admin permission-status should require admin role"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/permission-status", headers=user_headers)
        assert response.status_code == 403, "Should require admin role"


class TestAdminLiveReadinessScore:
    """GET /api/phase4/admin/live-readiness-score - Admin live readiness score"""

    def test_live_readiness_score_returns_200(self, admin_headers):
        """GET live-readiness-score should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/live-readiness-score", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_live_readiness_score_response_format(self, admin_headers):
        """GET live-readiness-score should return proper format"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/live-readiness-score", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "readiness_score" in data, "Must have readiness_score"
        assert "permission_ready" in data, "Must have permission_ready"
        assert "risk_engine_pass" in data, "Must have risk_engine_pass"
        assert "execution_simulation_pass" in data, "Must have execution_simulation_pass"
        assert "correlation_model_pass" in data, "Must have correlation_model_pass"
        assert "hardening_checklist_pass" in data, "Must have hardening_checklist_pass"
        assert "release_gate_status" in data, "Must have release_gate_status"
        assert "live_activation" in data, "Must have live_activation"
        assert "critical_blockers" in data, "Must have critical_blockers"
        
        # Validate types
        assert isinstance(data["readiness_score"], (int, float))
        assert isinstance(data["permission_ready"], bool)
        assert isinstance(data["critical_blockers"], list)
        assert data["release_gate_status"] in ["PASS", "WARNING", "BLOCKED"]
        assert data["live_activation"] in ["disabled", "guarded", "enabled"]

    def test_live_readiness_score_requires_admin(self, user_headers):
        """GET live-readiness-score should require admin role"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/live-readiness-score", headers=user_headers)
        assert response.status_code == 403


class TestAdminReleaseGate:
    """GET /api/phase4/admin/release-gate - Admin release gate status"""

    def test_release_gate_returns_200(self, admin_headers):
        """GET release-gate should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/release-gate", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_release_gate_response_format(self, admin_headers):
        """GET release-gate should return proper format"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/release-gate", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "status" in data, "Must have status"
        assert "reasons" in data, "Must have reasons"
        assert "live_activation" in data, "Must have live_activation"
        
        # Validate values
        assert data["status"] in ["PASS", "WARNING", "BLOCKED"]
        assert isinstance(data["reasons"], list)

    def test_release_gate_requires_admin(self, user_headers):
        """GET release-gate should require admin role"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/release-gate", headers=user_headers)
        assert response.status_code == 403


class TestUserTestOrder:
    """POST /api/phase4/test-order - User test order (blocked with invalid credentials)"""

    def test_test_order_blocked_with_invalid_credentials(self, user_headers):
        """POST test-order should return 400 (not 500) when credentials are invalid"""
        # With fake credentials saved earlier, test order should be blocked gracefully
        response = requests.post(f"{BASE_URL}/api/phase4/test-order", headers=user_headers)
        
        # Should NOT be 500 - that would be unhandled error
        assert response.status_code != 500, f"Should not return 500 server error, got: {response.status_code}"
        
        # Should be 400 (permission check failed) or similar client error
        assert response.status_code in [400, 403], f"Expected 400 or 403 for blocked order, got: {response.status_code}"
        
        # Check error message
        data = response.json()
        assert "detail" in data, "Should have error detail"

    def test_test_order_requires_user_role(self, admin_headers):
        """POST test-order should only work for user role, not admin"""
        response = requests.post(f"{BASE_URL}/api/phase4/test-order", headers=admin_headers)
        # Admin should be forbidden (test order is user-only)
        assert response.status_code == 403, f"Admin should not be able to send test order, got: {response.status_code}"

    def test_test_order_requires_auth(self):
        """POST test-order should require authentication"""
        response = requests.post(f"{BASE_URL}/api/phase4/test-order")
        assert response.status_code == 401


class TestAdminExecutionQuality:
    """GET /api/phase4/admin/execution-quality - Admin execution quality list"""

    def test_admin_execution_quality_returns_200(self, admin_headers):
        """GET admin execution-quality should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_admin_execution_quality_is_list(self, admin_headers):
        """GET admin execution-quality should return a list"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

    def test_admin_execution_quality_requires_admin(self, user_headers):
        """GET admin execution-quality should require admin role"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=user_headers)
        assert response.status_code == 403
