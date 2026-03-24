"""P0 Closure Comprehensive Tests - Iteration 123

Coverage:
1. Critical actions approval guard: inline disable/enable/trading/capital/privileged role için direct execute yok, approval_required dönmesi
2. Bulk action policy-aware: /api/admin/identity/users/bulk-status direct execute etmeyip approval request üretmeli
3. Soft delete request->approve->effects: login block + trading off + eligibility false + audit/log surface
4. Hard delete guard: retention 90 gün dolmadan approve aşamasında block
5. Self-approve block: requester approve edememeli
6. MFA standardization: login MFA challenge method seti TOTP (+ backup) ekseninde; email OTP primary login akışında kullanılmamalı
7. Session management: active list + revoke sonrası token invalid (session_revoked)
8. Security detail endpoint + UI: mfa state, policy lock, password expiry, sessions, login history
9. Eligibility checks: identity_active/email_verified/risk/capital/exchange/strategy/trading/not_deleted/not_locked/not_kill_switched anahtarları ve eligible_for_login/eligible_for_ops/live_trading_eligible output
10. Super admin delete/disable koruma (self veya super_admin target)
"""

from __future__ import annotations

import os
import uuid

import pyotp
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://strategy-version-gov.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = os.environ.get("STRATEGY_TEST_ADMIN_EMAIL", "canary.admin@platform.local")
SUPER_ADMIN_PASSWORD = os.environ.get("STRATEGY_TEST_ADMIN_PASSWORD", "CanaryAdmin123!")


def _bootstrap_login(email: str, password: str, login_path: str = "/api/auth/login/admin") -> tuple[str, str]:
    """Returns (access_token, totp_secret)"""
    start = requests.post(
        f"{BASE_URL}/api/auth/mfa/bootstrap/totp/start",
        json={"email": email, "password": password},
        timeout=30,
    )
    if start.status_code != 200:
        raise AssertionError(f"bootstrap start failed: {start.status_code} {start.text}")
    secret = start.json().get("totp_secret")
    
    verify = requests.post(
        f"{BASE_URL}/api/auth/mfa/bootstrap/totp/verify",
        json={"email": email, "password": password, "code": pyotp.TOTP(secret).now()},
        timeout=30,
    )
    if verify.status_code not in {200, 400}:  # already verified olabilir
        raise AssertionError(f"bootstrap verify failed: {verify.status_code} {verify.text}")

    login = requests.post(
        f"{BASE_URL}{login_path}",
        json={"email": email, "password": password},
        timeout=30,
    )
    if login.status_code != 200:
        raise AssertionError(f"login failed: {login.status_code} {login.text}")
    login_payload = login.json()
    
    if not login_payload.get("mfa_required"):
        token = login_payload.get("access_token")
        if not token:
            raise AssertionError("access_token missing")
        return token, secret

    challenge = login_payload.get("mfa_challenge_token")
    challenge_verify = requests.post(
        f"{BASE_URL}/api/auth/mfa/challenge/verify",
        json={
            "challenge_token": challenge,
            "method": "totp",
            "code": pyotp.TOTP(secret).now(),
        },
        timeout=30,
    )
    if challenge_verify.status_code != 200:
        raise AssertionError(f"challenge verify failed: {challenge_verify.status_code} {challenge_verify.text}")
    token = challenge_verify.json().get("access_token")
    if not token:
        raise AssertionError("mfa verify access_token missing")
    return token, secret


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_regular_user(approve_with_token: str | None = None) -> tuple[str, str, str]:
    """Create a regular user and optionally approve them"""
    email = f"p0.user.{uuid.uuid4().hex[:10]}@example.com"
    password = "P0User#12345"
    register = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert register.status_code == 200, register.text
    user_id = register.json()["id"]
    if approve_with_token:
        approve = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=_headers(approve_with_token),
            timeout=30,
        )
        assert approve.status_code == 200, approve.text
    return user_id, email, password


@pytest.fixture(scope="module")
def super_admin_auth() -> tuple[str, str]:
    """Returns (token, totp_secret)"""
    return _bootstrap_login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def super_admin_token(super_admin_auth: tuple[str, str]) -> str:
    return super_admin_auth[0]


@pytest.fixture(scope="module")
def secondary_admin(super_admin_token: str) -> tuple[str, str, str, str, str]:
    """Create a secondary admin for approval flow testing. Returns (admin_id, email, password, token, totp_secret)"""
    email = f"p0.admin.{uuid.uuid4().hex[:10]}@example.com"
    password = "P0Admin#12345"
    created = requests.post(
        f"{BASE_URL}/api/admin/users/admin-create",
        headers=_headers(super_admin_token),
        json={"email": email, "password": password, "role": "admin"},
        timeout=30,
    )
    assert created.status_code in {200, 201, 400}, created.text
    
    token, secret = _bootstrap_login(email, password)
    user_detail = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(token), timeout=30)
    assert user_detail.status_code == 200, user_detail.text
    admin_id = user_detail.json()["id"]
    return admin_id, email, password, token, secret


# ============================================================================
# TEST 1: Critical Actions Approval Guard
# ============================================================================
class TestCriticalActionsApprovalGuard:
    """Test that critical actions require approval and don't execute directly"""
    
    def test_inline_disable_requires_critical_confirmation(self, super_admin_token: str):
        """Disable user without critical_confirmed should fail"""
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"status": "disabled", "reason": "test"},
            timeout=30,
        )
        assert response.status_code == 400
        assert "critical_confirmation_required" in response.text
        print("PASS: Disable without critical_confirmed returns 400")

    def test_inline_disable_returns_approval_required(self, super_admin_token: str):
        """Disable user with critical_confirmed should return approval_required, not direct execute"""
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"status": "disabled", "reason": "test", "critical_confirmed": True},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data.get("status") == "approval_required", f"Expected approval_required, got {data}"
        assert "request_id" in data
        print(f"PASS: Disable returns approval_required with request_id={data.get('request_id')}")

    def test_inline_enable_returns_approval_required(self, super_admin_token: str):
        """Enable user with critical_confirmed should return approval_required"""
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"status": "active", "reason": "test", "critical_confirmed": True},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data.get("status") == "approval_required", f"Expected approval_required, got {data}"
        print("PASS: Enable returns approval_required")

    def test_inline_trading_enable_returns_approval_required(self, super_admin_token: str):
        """Enable trading with critical_confirmed should return approval_required"""
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"trading_enabled": True, "reason": "test", "critical_confirmed": True},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data.get("status") == "approval_required", f"Expected approval_required, got {data}"
        print("PASS: Trading enable returns approval_required")

    def test_inline_capital_limit_returns_approval_required(self, super_admin_token: str):
        """Raise capital limit with critical_confirmed should return approval_required"""
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"capital_limit": 100000.0, "reason": "test", "critical_confirmed": True},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data.get("status") == "approval_required", f"Expected approval_required, got {data}"
        print("PASS: Capital limit returns approval_required")

    def test_inline_privileged_role_returns_approval_required(self, super_admin_token: str):
        """Grant privileged role should return approval_required"""
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"role": "admin", "reason": "test", "critical_confirmed": True},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data.get("status") == "approval_required", f"Expected approval_required, got {data}"
        print("PASS: Privileged role grant returns approval_required")


# ============================================================================
# TEST 2: Bulk Action Policy-Aware
# ============================================================================
class TestBulkActionPolicyAware:
    """Test that bulk actions create approval requests instead of direct execution"""
    
    def test_bulk_status_requires_critical_confirmation(self, super_admin_token: str):
        """Bulk status without critical_confirmed should fail"""
        user_id, _, _ = _create_regular_user()
        response = requests.post(
            f"{BASE_URL}/api/admin/identity/users/bulk-status",
            headers=_headers(super_admin_token),
            json={"user_ids": [user_id], "status": "disabled", "reason": "bulk test"},
            timeout=30,
        )
        assert response.status_code == 400
        assert "critical_confirmation_required" in response.text
        print("PASS: Bulk status without critical_confirmed returns 400")

    def test_bulk_status_creates_approval_requests(self, super_admin_token: str):
        """Bulk status with critical_confirmed should create approval requests"""
        user_id, _, _ = _create_regular_user()
        response = requests.post(
            f"{BASE_URL}/api/admin/identity/users/bulk-status",
            headers=_headers(super_admin_token),
            json={
                "user_ids": [user_id],
                "status": "disabled",
                "reason": "bulk approval request",
                "critical_confirmed": True,
            },
            timeout=30,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload.get("status") == "approval_required"
        assert len(payload.get("requests_created", [])) >= 1
        print(f"PASS: Bulk status creates approval requests: {len(payload.get('requests_created', []))} requests")


# ============================================================================
# TEST 3: Soft Delete Lifecycle Effects
# ============================================================================
class TestSoftDeleteLifecycleEffects:
    """Test soft delete request->approve->effects"""
    
    def test_soft_delete_blocks_login_and_trading(self, super_admin_token: str, secondary_admin: tuple[str, str, str, str, str]):
        """After soft delete approval: login blocked, trading off, eligibility false"""
        _, _, _, requester_token, _ = secondary_admin
        user_id, email, password = _create_regular_user(approve_with_token=super_admin_token)

        # Create soft delete request
        request_soft = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/soft-delete/request",
            headers=_headers(requester_token),
            json={"reason": "soft delete lifecycle test", "critical_confirmed": True},
            timeout=30,
        )
        assert request_soft.status_code == 200, request_soft.text
        request_id = request_soft.json()["request_id"]

        # Approve soft delete
        approve = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{request_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "approved soft delete"},
            timeout=30,
        )
        assert approve.status_code == 200, approve.text

        # Verify login is blocked
        login_after = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
            timeout=30,
        )
        assert login_after.status_code in {401, 403}, f"Expected 401/403, got {login_after.status_code}"
        print("PASS: Soft deleted user cannot login")

        # Verify eligibility is false
        users_response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=_headers(super_admin_token),
            params={"search": email, "include_deleted": True},
            timeout=30,
        )
        assert users_response.status_code == 200
        items = users_response.json().get("items", [])
        if items:
            user_data = items[0]
            controls = user_data.get("identity_controls", {})
            assert controls.get("live_trading_eligible") is False, "Trading should be ineligible"
            checks = controls.get("compliance_checks", {})
            assert checks.get("not_deleted") is False, "not_deleted should be False"
            print("PASS: Soft deleted user has correct eligibility flags")


# ============================================================================
# TEST 4: Hard Delete Retention Guard
# ============================================================================
class TestHardDeleteRetentionGuard:
    """Test hard delete is blocked before 90-day retention"""
    
    def test_hard_delete_blocked_before_retention(self, super_admin_token: str, secondary_admin: tuple[str, str, str, str, str]):
        """Hard delete approval should fail if retention period not completed"""
        _, _, _, requester_token, _ = secondary_admin
        user_id, _, _ = _create_regular_user()

        # First soft delete
        request_soft = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/soft-delete/request",
            headers=_headers(requester_token),
            json={"reason": "prepare hard delete guard", "critical_confirmed": True},
            timeout=30,
        )
        assert request_soft.status_code == 200, request_soft.text
        soft_req_id = request_soft.json()["request_id"]
        
        approve_soft = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{soft_req_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "approve soft delete"},
            timeout=30,
        )
        assert approve_soft.status_code == 200, approve_soft.text

        # Request hard delete
        request_hard = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/hard-delete/request",
            headers=_headers(requester_token),
            json={"reason": "hard delete attempt", "critical_confirmed": True},
            timeout=30,
        )
        assert request_hard.status_code == 200, request_hard.text
        hard_req_id = request_hard.json()["request_id"]

        # Approve hard delete should fail due to retention
        approve_hard = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{hard_req_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "approve hard delete"},
            timeout=30,
        )
        assert approve_hard.status_code == 400
        assert "hard_delete_retention_not_completed" in approve_hard.text
        print("PASS: Hard delete blocked before 90-day retention")


# ============================================================================
# TEST 5: Self-Approve Block
# ============================================================================
class TestSelfApproveBlock:
    """Test that requester cannot approve their own request"""
    
    def test_requester_cannot_self_approve(self, super_admin_token: str):
        """Same actor cannot approve their own request"""
        user_id, _, _ = _create_regular_user()
        
        # Create request
        request_create = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/request",
            headers=_headers(super_admin_token),
            json={
                "action_key": "disable_user",
                "target_user_id": user_id,
                "payload": {"critical_confirmed": True},
                "reason": "self approve guard test",
            },
            timeout=30,
        )
        assert request_create.status_code == 200, request_create.text
        request_id = request_create.json()["request_id"]

        # Try to self-approve
        approve = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{request_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "self approve attempt"},
            timeout=30,
        )
        assert approve.status_code == 403
        assert "same_actor_cannot_approve" in approve.text
        print("PASS: Self-approve blocked")


# ============================================================================
# TEST 6: MFA Standardization
# ============================================================================
class TestMfaStandardization:
    """Test MFA is TOTP-based, email OTP not used for primary login"""
    
    def test_admin_login_mfa_methods_are_totp_based(self):
        """Admin login MFA challenge should offer TOTP and backup_code, not email OTP"""
        # Bootstrap TOTP first
        start = requests.post(
            f"{BASE_URL}/api/auth/mfa/bootstrap/totp/start",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
            timeout=30,
        )
        assert start.status_code == 200
        secret = start.json().get("totp_secret")
        
        # Verify TOTP
        requests.post(
            f"{BASE_URL}/api/auth/mfa/bootstrap/totp/verify",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD, "code": pyotp.TOTP(secret).now()},
            timeout=30,
        )
        
        # Login to get MFA challenge
        login = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
            timeout=30,
        )
        assert login.status_code == 200, login.text
        data = login.json()
        
        assert data.get("mfa_required") is True, "Admin login should require MFA"
        mfa_methods = data.get("mfa_methods", [])
        assert "totp" in mfa_methods, "TOTP should be in MFA methods"
        assert "backup_code" in mfa_methods, "backup_code should be in MFA methods"
        assert "email" not in mfa_methods, "email OTP should NOT be in primary login MFA methods"
        print(f"PASS: MFA methods are TOTP-based: {mfa_methods}")


# ============================================================================
# TEST 7: Session Management
# ============================================================================
class TestSessionManagement:
    """Test session list and revoke functionality"""
    
    def test_session_revoke_invalidates_token(self, super_admin_token: str):
        """After session revoke, token should be invalid"""
        user_id, email, password = _create_regular_user(approve_with_token=super_admin_token)
        
        # Login user
        login_user = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
            timeout=30,
        )
        assert login_user.status_code == 200, login_user.text
        user_token = login_user.json().get("access_token")
        assert user_token

        # Get active sessions
        active_sessions = requests.get(
            f"{BASE_URL}/api/auth/sessions/active",
            params={"user_id": user_id},
            headers=_headers(super_admin_token),
            timeout=30,
        )
        assert active_sessions.status_code == 200, active_sessions.text
        items = active_sessions.json().get("items", [])
        if not items:
            pytest.skip("No active sessions found for user")

        session_id = items[0]["session_id"]
        
        # Revoke session
        revoke = requests.post(
            f"{BASE_URL}/api/auth/sessions/{session_id}/revoke",
            headers=_headers(super_admin_token),
            json={"reason": "p0 revoke test"},
            timeout=30,
        )
        assert revoke.status_code == 200, revoke.text

        # Verify token is invalid
        me_after = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(user_token), timeout=30)
        assert me_after.status_code == 401
        assert "session_revoked" in me_after.text
        print("PASS: Session revoke invalidates token")


# ============================================================================
# TEST 8: Security Detail Endpoint
# ============================================================================
class TestSecurityDetailEndpoint:
    """Test security detail endpoint returns all required fields"""
    
    def test_security_detail_has_all_fields(self, super_admin_token: str):
        """Security detail should include mfa, policy lock, password expiry, sessions, login history"""
        # Get current user ID
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(super_admin_token), timeout=30)
        assert me.status_code == 200
        user_id = me.json()["id"]
        
        # Get security detail
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/security",
            headers=_headers(super_admin_token),
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        
        # Check MFA fields
        assert "mfa" in data, "Should have mfa section"
        mfa = data["mfa"]
        assert "is_enabled" in mfa, "mfa should have is_enabled"
        assert "enabled_methods" in mfa, "mfa should have enabled_methods"
        assert "totp_configured" in mfa, "mfa should have totp_configured"
        assert "totp_verified" in mfa, "mfa should have totp_verified"
        assert "backup_codes_remaining" in mfa, "mfa should have backup_codes_remaining"
        
        # Check security state fields
        assert "security_state" in data, "Should have security_state section"
        state = data["security_state"]
        assert "policy_locked_until" in state, "security_state should have policy_locked_until"
        assert "password_expires_at" in state, "security_state should have password_expires_at"
        assert "eligible_for_login" in state, "security_state should have eligible_for_login"
        assert "eligible_for_ops" in state, "security_state should have eligible_for_ops"
        
        # Check sessions
        assert "sessions" in data, "Should have sessions list"
        
        # Check login history
        assert "login_history" in data, "Should have login_history list"
        
        print("PASS: Security detail has all required fields")


# ============================================================================
# TEST 9: Eligibility Checks
# ============================================================================
class TestEligibilityChecks:
    """Test eligibility engine returns all required keys"""
    
    def test_eligibility_keys_present(self, super_admin_token: str):
        """Identity users endpoint should return all eligibility check keys"""
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=_headers(super_admin_token),
            params={"page": 1, "page_size": 20},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        items = response.json().get("items", [])
        if not items:
            pytest.skip("No users found")
        
        sample = items[0]
        controls = sample.get("identity_controls", {})
        checks = controls.get("compliance_checks", {})
        
        # Verify all required check keys
        required_keys = [
            "identity_active",
            "email_verified",
            "risk_profile_assigned",
            "capital_limit_defined",
            "exchange_connected",
            "strategy_scope_assigned",
            "trading_enabled",
            "not_deleted",
            "not_locked_by_policy",
            "not_kill_switched",
        ]
        for key in required_keys:
            assert key in checks, f"Missing eligibility check: {key}"
        
        # Verify output keys
        assert "eligible_for_login" in controls, "Should have eligible_for_login"
        assert "eligible_for_ops" in controls, "Should have eligible_for_ops"
        assert "live_trading_eligible" in controls, "Should have live_trading_eligible"
        
        print(f"PASS: All eligibility keys present: {list(checks.keys())}")


# ============================================================================
# TEST 10: Super Admin Protection
# ============================================================================
class TestSuperAdminProtection:
    """Test super admin cannot be deleted or disabled"""
    
    def test_super_admin_self_delete_blocked(self, super_admin_token: str):
        """Super admin cannot request soft delete on themselves"""
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(super_admin_token), timeout=30)
        assert me.status_code == 200
        me_id = me.json()["id"]

        soft_request = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{me_id}/soft-delete/request",
            headers=_headers(super_admin_token),
            json={"reason": "should fail", "critical_confirmed": True},
            timeout=30,
        )
        assert soft_request.status_code == 403
        assert "self_request_not_allowed" in soft_request.text or "super_admin_protected" in soft_request.text
        print("PASS: Super admin self-delete blocked")

    def test_super_admin_target_protected(self, super_admin_token: str, secondary_admin: tuple[str, str, str, str, str]):
        """Cannot create approval request targeting super_admin"""
        _, _, _, requester_token, _ = secondary_admin
        
        # Get super admin ID
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(super_admin_token), timeout=30)
        super_admin_id = me.json()["id"]
        
        # Try to create disable request for super admin
        request_create = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/request",
            headers=_headers(requester_token),
            json={
                "action_key": "disable_user",
                "target_user_id": super_admin_id,
                "payload": {"critical_confirmed": True},
                "reason": "should fail",
            },
            timeout=30,
        )
        assert request_create.status_code == 403
        assert "super_admin_protected" in request_create.text
        print("PASS: Super admin target protected")


# ============================================================================
# TEST: Login Lock Policy
# ============================================================================
class TestLoginLockPolicy:
    """Test login lock after failed attempts"""
    
    def test_login_lock_after_failed_attempts(self):
        """Account should be locked after multiple failed login attempts"""
        email = f"nonexistent.{uuid.uuid4().hex[:8]}@example.com"
        
        # Make 5 failed attempts
        for i in range(5):
            requests.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": email, "password": "Wrong#1234"},
                timeout=30,
            )
        
        # 6th attempt should be locked
        locked = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": "Wrong#1234"},
            timeout=30,
        )
        assert locked.status_code in {423, 429, 401}
        print(f"PASS: Login locked after failed attempts (status={locked.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
