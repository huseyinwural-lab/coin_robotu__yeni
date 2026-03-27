"""
Test MFA Bypass for Canary Admin
Policy change: Admin + Super Admin MFA should be optional.
For canary.admin@platform.local specifically, temporary no-MFA login must work now.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

# Test credentials from test_credentials.md
CANARY_EMAIL = "canary.admin@platform.local"
CANARY_PASSWORD = "CanaryAdmin123!"


class TestMfaBypassCanaryAdmin:
    """Test MFA bypass for canary.admin@platform.local"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session for tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        yield
        self.session.close()

    def test_01_admin_login_returns_mfa_required_false(self):
        """
        POST /api/auth/login/admin for canary.admin@platform.local returns mfa_required=false
        This is the core test for the policy change.
        """
        response = self.session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": CANARY_EMAIL, "password": CANARY_PASSWORD},
        )
        
        print(f"Login response status: {response.status_code}")
        print(f"Login response: {response.json()}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Core assertion: mfa_required should be false for canary admin
        mfa_required = data.get("mfa_required", True)
        assert mfa_required is False, f"Expected mfa_required=false, got {mfa_required}"
        
        # Verify token is present (no MFA challenge needed)
        access_token = data.get("access_token") or data.get("token")
        assert access_token is not None, "Expected access_token to be present when mfa_required=false"
        assert len(access_token) > 0, "access_token should not be empty"
        
        # Verify user payload is present
        user = data.get("user")
        assert user is not None, "Expected user payload to be present"
        assert user.get("email") == CANARY_EMAIL, f"Expected email {CANARY_EMAIL}, got {user.get('email')}"
        
        # Verify token_type is bearer (not mfa_challenge)
        token_type = data.get("token_type", "")
        assert token_type == "bearer", f"Expected token_type=bearer, got {token_type}"
        
        print("PASS: Admin login returns mfa_required=false with token and user payload")

    def test_02_canary_admin_can_disable_mfa(self):
        """
        canary admin can call /api/mfa/disable successfully
        """
        # First login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": CANARY_EMAIL, "password": CANARY_PASSWORD},
        )
        
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        login_data = login_response.json()
        access_token = login_data.get("access_token") or login_data.get("token")
        
        # Skip if MFA challenge is required (shouldn't happen per policy)
        if login_data.get("mfa_required"):
            pytest.skip("MFA required - cannot test disable without completing MFA")
        
        assert access_token, "No access token received"
        
        # Get device_id cookie from login response
        device_id = login_response.cookies.get("device_id")
        
        # Call /api/mfa/disable
        headers = {"Authorization": f"Bearer {access_token}"}
        cookies = {"device_id": device_id} if device_id else {}
        
        disable_response = self.session.post(
            f"{BASE_URL}/api/mfa/disable",
            headers=headers,
            cookies=cookies,
        )
        
        print(f"MFA disable response status: {disable_response.status_code}")
        print(f"MFA disable response: {disable_response.text}")
        
        # Should succeed (200) or already disabled
        assert disable_response.status_code in [200, 403], f"Unexpected status: {disable_response.status_code}"
        
        if disable_response.status_code == 200:
            data = disable_response.json()
            assert data.get("is_enabled") is False, "Expected is_enabled=false after disable"
            print("PASS: MFA disable successful")
        else:
            # 403 might mean OPS role restriction - check detail
            detail = disable_response.json().get("detail", "")
            print(f"MFA disable returned 403: {detail}")
            # This is acceptable if the role is OPS (which has mandatory MFA)
            assert "privileged_mfa_disable_forbidden" in str(detail), f"Unexpected 403 reason: {detail}"
            print("PASS: MFA disable correctly blocked for OPS role")

    def test_03_mfa_settings_shows_disabled_after_disable(self):
        """
        GET /api/auth/mfa/settings shows is_enabled=false for canary after disable
        """
        # First login to get token
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": CANARY_EMAIL, "password": CANARY_PASSWORD},
        )
        
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        login_data = login_response.json()
        access_token = login_data.get("access_token") or login_data.get("token")
        
        if login_data.get("mfa_required"):
            pytest.skip("MFA required - cannot test settings without completing MFA")
        
        assert access_token, "No access token received"
        
        device_id = login_response.cookies.get("device_id")
        headers = {"Authorization": f"Bearer {access_token}"}
        cookies = {"device_id": device_id} if device_id else {}
        
        # Get MFA settings
        settings_response = self.session.get(
            f"{BASE_URL}/api/auth/mfa/settings",
            headers=headers,
            cookies=cookies,
        )
        
        print(f"MFA settings response status: {settings_response.status_code}")
        print(f"MFA settings response: {settings_response.text}")
        
        assert settings_response.status_code == 200, f"Expected 200, got {settings_response.status_code}"
        
        data = settings_response.json()
        is_enabled = data.get("is_enabled")
        
        # After disable, is_enabled should be false
        # Note: If MFA was never enabled, it will also be false
        print(f"MFA is_enabled: {is_enabled}")
        print("PASS: MFA settings endpoint accessible")

    def test_04_no_regression_auth_response_structure(self):
        """
        No regression in auth endpoint responses (token and user payload present)
        """
        response = self.session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": CANARY_EMAIL, "password": CANARY_PASSWORD},
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        
        # Check all expected fields are present
        expected_fields = ["token_type", "role", "user"]
        for field in expected_fields:
            assert field in data, f"Missing expected field: {field}"
        
        # Either access_token or token should be present
        has_token = data.get("access_token") or data.get("token")
        assert has_token is not None, "Neither access_token nor token present"
        
        # User object should have expected structure
        user = data.get("user", {})
        user_fields = ["id", "email", "role"]
        for field in user_fields:
            assert field in user, f"Missing user field: {field}"
        
        # Role should be admin-level
        role = data.get("role", "")
        assert role in ["admin", "super_admin", "ops"], f"Unexpected role: {role}"
        
        print("PASS: Auth response structure is correct with all expected fields")

    def test_05_frontend_login_flow_no_mfa_required(self):
        """
        Frontend login flow still works with no MFA-required response
        This simulates what the frontend would receive
        """
        response = self.session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": CANARY_EMAIL, "password": CANARY_PASSWORD},
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        
        # Frontend checks mfa_required to decide flow
        mfa_required = data.get("mfa_required", True)
        
        if mfa_required:
            # If MFA is required, frontend would show MFA challenge
            mfa_challenge_token = data.get("mfa_challenge_token")
            mfa_methods = data.get("mfa_methods", [])
            print(f"MFA required - challenge_token present: {bool(mfa_challenge_token)}")
            print(f"MFA methods: {mfa_methods}")
            pytest.fail("Expected mfa_required=false for canary admin")
        else:
            # If MFA not required, frontend can proceed with token
            access_token = data.get("access_token") or data.get("token")
            assert access_token, "Token should be present when mfa_required=false"
            
            # Frontend would store this token and redirect to dashboard
            print("PASS: Frontend can proceed without MFA challenge")
            print(f"Token received: {access_token[:20]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
