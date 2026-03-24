"""
Identity Control Layer Tests - Iteration 122
Tests for:
- MFA bootstrap endpoints (TOTP start/verify)
- Admin login with MFA challenge pattern
- Session management (active sessions, revoke)
- Identity control list endpoint with filters
- Inline update with approval_required pattern
- Bulk enable/disable
- Kill switch
- Approval flow endpoints
- Invite mocked flow
- Login history endpoint
"""
import os
import pytest
import requests
import pyotp

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestMfaBootstrapFlow:
    """MFA bootstrap endpoints for admin TOTP setup"""

    def test_mfa_bootstrap_totp_start(self):
        """Test /api/auth/mfa/bootstrap/totp/start - returns TOTP secret and URI"""
        response = requests.post(
            f"{BASE_URL}/api/auth/mfa/bootstrap/totp/start",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "totp_secret" in data, "Response should contain totp_secret"
        assert "otpauth_uri" in data, "Response should contain otpauth_uri"
        assert "user_id" in data, "Response should contain user_id"
        assert "email" in data, "Response should contain email"
        assert data["email"] == ADMIN_EMAIL
        print(f"TOTP bootstrap start successful: secret={data['totp_secret'][:8]}...")

    def test_mfa_bootstrap_totp_verify(self):
        """Test /api/auth/mfa/bootstrap/totp/verify - verifies TOTP code and enables MFA"""
        # First get the TOTP secret
        start_response = requests.post(
            f"{BASE_URL}/api/auth/mfa/bootstrap/totp/start",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert start_response.status_code == 200
        start_data = start_response.json()
        totp_secret = start_data["totp_secret"]

        # Generate valid TOTP code
        totp = pyotp.TOTP(totp_secret)
        valid_code = totp.now()

        # Verify the TOTP setup
        verify_response = requests.post(
            f"{BASE_URL}/api/auth/mfa/bootstrap/totp/verify",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "code": valid_code},
        )
        assert verify_response.status_code == 200, f"Expected 200, got {verify_response.status_code}: {verify_response.text}"
        verify_data = verify_response.json()
        assert verify_data.get("totp_verified") is True, "TOTP should be verified"
        assert "backup_codes" in verify_data, "Response should contain backup_codes"
        assert len(verify_data.get("backup_codes", [])) > 0, "Should have backup codes"
        print(f"TOTP bootstrap verify successful: backup_codes_count={len(verify_data.get('backup_codes', []))}")


class TestAdminLoginWithMfa:
    """Admin login flow with MFA challenge pattern"""

    @pytest.fixture(autouse=True)
    def setup_totp(self):
        """Ensure TOTP is set up before login tests"""
        # Start TOTP setup
        start_response = requests.post(
            f"{BASE_URL}/api/auth/mfa/bootstrap/totp/start",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if start_response.status_code == 200:
            self.totp_secret = start_response.json().get("totp_secret")
            # Verify TOTP
            totp = pyotp.TOTP(self.totp_secret)
            requests.post(
                f"{BASE_URL}/api/auth/mfa/bootstrap/totp/verify",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "code": totp.now()},
            )
        else:
            self.totp_secret = None

    def test_admin_login_returns_mfa_challenge(self):
        """Test /api/auth/login/admin returns mfa_required=true"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Admin login should require MFA
        assert data.get("mfa_required") is True, "Admin login should require MFA"
        assert "mfa_challenge_token" in data, "Response should contain mfa_challenge_token"
        assert "mfa_methods" in data, "Response should contain mfa_methods"
        assert "totp" in data.get("mfa_methods", []), "TOTP should be in allowed methods"
        print(f"Admin login MFA challenge: methods={data.get('mfa_methods')}")

    def test_mfa_challenge_verify_with_totp(self):
        """Test /api/auth/mfa/challenge/verify with TOTP code"""
        if not self.totp_secret:
            pytest.skip("TOTP not configured")

        # Get MFA challenge
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        challenge_token = login_data.get("mfa_challenge_token")
        assert challenge_token, "Should have challenge token"

        # Verify with TOTP
        totp = pyotp.TOTP(self.totp_secret)
        verify_response = requests.post(
            f"{BASE_URL}/api/auth/mfa/challenge/verify",
            json={
                "challenge_token": challenge_token,
                "method": "totp",
                "code": totp.now(),
            },
        )
        assert verify_response.status_code == 200, f"Expected 200, got {verify_response.status_code}: {verify_response.text}"
        verify_data = verify_response.json()
        assert "access_token" in verify_data, "Response should contain access_token"
        assert verify_data.get("mfa_required") is False, "MFA should no longer be required"
        print(f"MFA challenge verified successfully, got access_token")


def get_admin_token():
    """Helper to get admin token with MFA"""
    # Start TOTP setup
    start_response = requests.post(
        f"{BASE_URL}/api/auth/mfa/bootstrap/totp/start",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if start_response.status_code != 200:
        return None
    totp_secret = start_response.json().get("totp_secret")

    # Verify TOTP
    totp = pyotp.TOTP(totp_secret)
    requests.post(
        f"{BASE_URL}/api/auth/mfa/bootstrap/totp/verify",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "code": totp.now()},
    )

    # Login and get challenge
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if login_response.status_code != 200:
        return None
    login_data = login_response.json()
    challenge_token = login_data.get("mfa_challenge_token")

    # Verify MFA challenge
    totp = pyotp.TOTP(totp_secret)
    verify_response = requests.post(
        f"{BASE_URL}/api/auth/mfa/challenge/verify",
        json={
            "challenge_token": challenge_token,
            "method": "totp",
            "code": totp.now(),
        },
    )
    if verify_response.status_code != 200:
        return None
    return verify_response.json().get("access_token")


class TestSessionManagement:
    """Session management endpoints"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_get_active_sessions(self):
        """Test /api/auth/sessions/active"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/auth/sessions/active",
            headers=self.headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should contain items"
        assert "total" in data, "Response should contain total"
        if data["items"]:
            session = data["items"][0]
            assert "session_id" in session, "Session should have session_id"
            assert "user_id" in session, "Session should have user_id"
            assert "ip_address" in session, "Session should have ip_address"
        print(f"Active sessions: total={data['total']}")

    def test_revoke_session(self):
        """Test /api/auth/sessions/{id}/revoke"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Get sessions first
        sessions_response = requests.get(
            f"{BASE_URL}/api/auth/sessions/active",
            headers=self.headers,
        )
        if sessions_response.status_code != 200 or not sessions_response.json().get("items"):
            pytest.skip("No sessions to revoke")

        # We won't actually revoke our current session, just test the endpoint exists
        # by checking with a fake session ID
        response = requests.post(
            f"{BASE_URL}/api/auth/sessions/fake-session-id/revoke",
            headers=self.headers,
            json={"reason": "test_revoke"},
        )
        # Should return 404 for non-existent session
        assert response.status_code == 404, f"Expected 404 for fake session, got {response.status_code}"
        print("Session revoke endpoint working (404 for non-existent session)")


class TestIdentityControlUsers:
    """Identity control user list and management endpoints"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_list_identity_users(self):
        """Test /api/admin/identity/users with pagination"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"page": 1, "page_size": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should contain items"
        assert "pagination" in data, "Response should contain pagination"
        pagination = data["pagination"]
        assert "page" in pagination, "Pagination should have page"
        assert "page_size" in pagination, "Pagination should have page_size"
        assert "total" in pagination, "Pagination should have total"
        print(f"Identity users: total={pagination['total']}, page={pagination['page']}")

    def test_list_identity_users_with_filters(self):
        """Test /api/admin/identity/users with search/filter"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Test with search filter
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"search": "canary", "page": 1, "page_size": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        print(f"Search filter 'canary': found {len(data['items'])} users")

    def test_list_identity_users_with_role_filter(self):
        """Test /api/admin/identity/users with role filter"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"role": "super_admin", "page": 1, "page_size": 10},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        # All returned users should be super_admin
        for user in data["items"]:
            assert user["role"] == "super_admin", f"Expected super_admin role, got {user['role']}"
        print(f"Role filter 'super_admin': found {len(data['items'])} users")

    def test_identity_user_has_identity_controls(self):
        """Test that user response includes identity_controls and observability"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"page": 1, "page_size": 5},
        )
        assert response.status_code == 200
        data = response.json()
        if data["items"]:
            user = data["items"][0]
            assert "identity_controls" in user, "User should have identity_controls"
            assert "observability" in user, "User should have observability"
            ic = user["identity_controls"]
            assert "risk_status" in ic, "identity_controls should have risk_status"
            assert "trading_status" in ic, "identity_controls should have trading_status"
            assert "exchange_connected" in ic, "identity_controls should have exchange_connected"
            obs = user["observability"]
            assert "trade_count" in obs, "observability should have trade_count"
            assert "error_rate" in obs, "observability should have error_rate"
            print(f"User identity_controls: {ic}")


class TestInlineUpdateWithApproval:
    """Inline update endpoint with approval_required pattern"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_inline_update_status_active(self):
        """Test /api/admin/identity/users/{id}/inline for status=active"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Get a user first
        users_response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"page": 1, "page_size": 5},
        )
        if users_response.status_code != 200 or not users_response.json().get("items"):
            pytest.skip("No users to update")

        user = users_response.json()["items"][0]
        user_id = user["id"]

        # status=active artık kritik akışta approval gerektirir
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=self.headers,
            json={"status": "active", "reason": "test_inline_update", "critical_confirmed": True},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "approval_required", f"Unexpected status: {data}"
        print(f"Inline update status=active: {data.get('status')}")

    def test_inline_update_disable_requires_approval(self):
        """Test /api/admin/identity/users/{id}/inline for status=disabled requires approval"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Get a non-super_admin user
        users_response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"role": "user", "page": 1, "page_size": 5},
        )
        if users_response.status_code != 200 or not users_response.json().get("items"):
            pytest.skip("No user-role users to test")

        user = users_response.json()["items"][0]
        user_id = user["id"]

        # Try to disable - should require approval
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=self.headers,
            json={"status": "disabled", "reason": "test_disable_approval", "critical_confirmed": True},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "approval_required", f"Disable should require approval: {data}"
        assert "request_id" in data, "Should return request_id"
        print(f"Inline update status=disabled: approval_required, request_id={data.get('request_id')}")


class TestBulkStatusOperations:
    """Bulk enable/disable operations"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_bulk_status_endpoint_exists(self):
        """Test /api/admin/identity/users/bulk-status endpoint"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Test with empty user_ids - should return error
        response = requests.post(
            f"{BASE_URL}/api/admin/identity/users/bulk-status",
            headers=self.headers,
            json={"user_ids": [], "status": "disabled", "reason": "test_bulk"},
        )
        assert response.status_code == 400, f"Expected 400 for empty user_ids, got {response.status_code}"
        print("Bulk status endpoint working (400 for empty user_ids)")


class TestKillSwitch:
    """Kill switch endpoint"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_kill_switch_endpoint(self):
        """Test /api/admin/identity/users/{id}/kill-switch"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Get a non-super_admin user
        users_response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"role": "user", "page": 1, "page_size": 5},
        )
        if users_response.status_code != 200 or not users_response.json().get("items"):
            pytest.skip("No user-role users to test")

        user = users_response.json()["items"][0]
        user_id = user["id"]

        # Activate kill switch
        response = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/kill-switch",
            headers=self.headers,
            json={"active": True, "reason": "test_kill_switch"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("kill_switch_active") is True, "Kill switch should be active"
        print(f"Kill switch activated for user {user_id}")

        # Deactivate kill switch
        response = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/kill-switch",
            headers=self.headers,
            json={"active": False, "reason": "test_kill_switch_off"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("kill_switch_active") is False, "Kill switch should be inactive"
        print(f"Kill switch deactivated for user {user_id}")


class TestApprovalFlow:
    """Approval flow endpoints"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_list_approvals(self):
        """Test /api/admin/identity/approvals"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/approvals",
            headers=self.headers,
            params={"status_filter": "pending"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should contain items"
        print(f"Pending approvals: {len(data['items'])}")

    def test_list_approval_policies(self):
        """Test /api/admin/identity/approval-policies"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/approval-policies",
            headers=self.headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should contain items"
        if data["items"]:
            policy = data["items"][0]
            assert "action_key" in policy, "Policy should have action_key"
            assert "is_enabled" in policy, "Policy should have is_enabled"
            assert "required_approvals" in policy, "Policy should have required_approvals"
        print(f"Approval policies: {len(data['items'])}")

    def test_create_approval_request(self):
        """Test /api/admin/identity/approvals/request"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Get a non-super_admin user
        users_response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=self.headers,
            params={"role": "user", "page": 1, "page_size": 5},
        )
        if users_response.status_code != 200 or not users_response.json().get("items"):
            pytest.skip("No user-role users to test")

        user = users_response.json()["items"][0]
        user_id = user["id"]

        response = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/request",
            headers=self.headers,
            json={
                "action_key": "disable_user",
                "target_user_id": user_id,
                "payload": {"critical_confirmed": True},
                "reason": "test_approval_request",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "request_id" in data, "Response should contain request_id"
        assert data.get("status") == "pending", "Request should be pending"
        print(f"Approval request created: {data.get('request_id')}")


class TestInviteFlow:
    """Invite mocked flow endpoints"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_create_invite(self):
        """Test /api/admin/identity/invites (MOCKED)"""
        if not self.token:
            pytest.skip("Could not get admin token")

        import secrets
        test_email = f"test-invite-{secrets.token_hex(4)}@example.com"

        response = requests.post(
            f"{BASE_URL}/api/admin/identity/invites",
            headers=self.headers,
            json={
                "email": test_email,
                "invited_role": "user",
                "expires_hours": 24,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "invite_id" in data, "Response should contain invite_id"
        assert data.get("delivery_status") == "MOCKED_SENT", "Delivery should be MOCKED_SENT"
        assert "preview_token" in data, "Response should contain preview_token"
        print(f"Invite created (MOCKED): {data.get('invite_id')}, delivery={data.get('delivery_status')}")
        return data

    def test_list_invites(self):
        """Test /api/admin/identity/invites list"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/invites",
            headers=self.headers,
            params={"status_filter": "all"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should contain items"
        print(f"Invites: {len(data['items'])}")

    def test_accept_invite(self):
        """Test /api/admin/identity/invites/accept"""
        if not self.token:
            pytest.skip("Could not get admin token")

        # Create an invite first
        import secrets
        test_email = f"test-accept-{secrets.token_hex(4)}@example.com"

        create_response = requests.post(
            f"{BASE_URL}/api/admin/identity/invites",
            headers=self.headers,
            json={
                "email": test_email,
                "invited_role": "user",
                "expires_hours": 24,
            },
        )
        if create_response.status_code != 200:
            pytest.skip("Could not create invite")

        preview_token = create_response.json().get("preview_token")
        if not preview_token:
            pytest.skip("No preview_token in invite response")

        # Accept the invite
        accept_response = requests.post(
            f"{BASE_URL}/api/admin/identity/invites/accept",
            json={"preview_token": preview_token},
        )
        assert accept_response.status_code == 200, f"Expected 200, got {accept_response.status_code}: {accept_response.text}"
        data = accept_response.json()
        assert data.get("status") == "accepted", "Invite should be accepted"
        print(f"Invite accepted: {data.get('invite_id')}")


class TestLoginHistory:
    """Login history endpoint"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        self.token = get_admin_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def test_login_history(self):
        """Test /api/admin/identity/login-history"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/login-history",
            headers=self.headers,
            params={"limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data, "Response should contain items"
        if data["items"]:
            event = data["items"][0]
            assert "email" in event, "Event should have email"
            assert "outcome" in event, "Event should have outcome"
            assert "ip_address" in event, "Event should have ip_address"
            assert "user_agent" in event, "Event should have user_agent"
            assert "device_fingerprint" in event, "Event should have device_fingerprint"
        print(f"Login history: {len(data['items'])} events")

    def test_login_history_with_email_filter(self):
        """Test /api/admin/identity/login-history with email filter"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/login-history",
            headers=self.headers,
            params={"email": "canary", "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        # All events should contain 'canary' in email
        for event in data["items"]:
            assert "canary" in event["email"].lower(), f"Email should contain 'canary': {event['email']}"
        print(f"Login history (email=canary): {len(data['items'])} events")

    def test_login_history_with_outcome_filter(self):
        """Test /api/admin/identity/login-history with outcome filter"""
        if not self.token:
            pytest.skip("Could not get admin token")

        response = requests.get(
            f"{BASE_URL}/api/admin/identity/login-history",
            headers=self.headers,
            params={"outcome": "SUCCESS", "limit": 50},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "items" in data
        # All events should have SUCCESS outcome
        for event in data["items"]:
            assert event["outcome"] == "SUCCESS", f"Outcome should be SUCCESS: {event['outcome']}"
        print(f"Login history (outcome=SUCCESS): {len(data['items'])} events")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
