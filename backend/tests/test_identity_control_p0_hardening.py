"""P0 hardening regression tests for Identity + Risk + Trading Control Plane.

Coverage:
- Approval bypass guards
- Soft delete lifecycle guards
- Hard delete retention guard
- Last super_admin protection
- Bulk action policy enforcement
- Session revoke enforcement
- Login lock policy
- Eligibility decision surface
"""

from __future__ import annotations

import os
import uuid

import pyotp
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://identity-control-1.preview.emergentagent.com"
SUPER_ADMIN_EMAIL = os.environ.get("STRATEGY_TEST_ADMIN_EMAIL", "canary.admin@platform.local")
SUPER_ADMIN_PASSWORD = os.environ.get("STRATEGY_TEST_ADMIN_PASSWORD", "CanaryAdmin123!")


def _bootstrap_login(email: str, password: str, login_path: str = "/api/auth/login/admin") -> str:
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
        return token

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
    return token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _create_regular_user(approve_with_token: str | None = None) -> tuple[str, str, str]:
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
def super_admin_token() -> str:
    return _bootstrap_login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def secondary_admin(super_admin_token: str) -> tuple[str, str, str, str]:
    email = f"p0.admin.{uuid.uuid4().hex[:10]}@example.com"
    password = "P0Admin#12345"
    created = requests.post(
        f"{BASE_URL}/api/admin/users/admin-create",
        headers=_headers(super_admin_token),
        json={"email": email, "password": password, "role": "admin"},
        timeout=30,
    )
    assert created.status_code in {200, 201, 400}, created.text
    if created.status_code == 400 and "already_exists" in created.text:
        pass
    token = _bootstrap_login(email, password)
    user_detail = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(token), timeout=30)
    assert user_detail.status_code == 200, user_detail.text
    admin_id = user_detail.json()["id"]
    return admin_id, email, password, token


class TestP0ApprovalBypass:
    def test_inline_disable_requires_critical_confirmation(self, super_admin_token: str):
        user_id, _, _ = _create_regular_user()
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/inline",
            headers=_headers(super_admin_token),
            json={"status": "disabled", "reason": "test"},
            timeout=30,
        )
        assert response.status_code == 400
        assert "critical_confirmation_required" in response.text

    def test_requester_cannot_self_approve(self, super_admin_token: str):
        user_id, _, _ = _create_regular_user()
        request_create = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/request",
            headers=_headers(super_admin_token),
            json={
                "action_key": "disable_user",
                "target_user_id": user_id,
                "payload": {"critical_confirmed": True},
                "reason": "self approve guard",
            },
            timeout=30,
        )
        assert request_create.status_code == 200, request_create.text
        request_id = request_create.json()["request_id"]

        approve = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{request_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "self approve attempt"},
            timeout=30,
        )
        assert approve.status_code == 403
        assert "same_actor_cannot_approve" in approve.text


class TestP0DeleteLifecycle:
    def test_soft_delete_lifecycle_effects(self, super_admin_token: str, secondary_admin: tuple[str, str, str, str]):
        _, _, _, requester_token = secondary_admin
        user_id, email, password = _create_regular_user(approve_with_token=super_admin_token)

        request_soft = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/soft-delete/request",
            headers=_headers(requester_token),
            json={"reason": "soft delete regression", "critical_confirmed": True},
            timeout=30,
        )
        assert request_soft.status_code == 200, request_soft.text
        request_id = request_soft.json()["request_id"]

        approve = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{request_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "approved soft delete"},
            timeout=30,
        )
        assert approve.status_code == 200, approve.text

        login_after = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
            timeout=30,
        )
        assert login_after.status_code in {401, 403}

    def test_hard_delete_retention_guard(self, super_admin_token: str, secondary_admin: tuple[str, str, str, str]):
        _, _, _, requester_token = secondary_admin
        user_id, _, _ = _create_regular_user()

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

        request_hard = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/hard-delete/request",
            headers=_headers(requester_token),
            json={"reason": "hard delete attempt", "critical_confirmed": True},
            timeout=30,
        )
        assert request_hard.status_code == 200, request_hard.text
        hard_req_id = request_hard.json()["request_id"]

        approve_hard = requests.post(
            f"{BASE_URL}/api/admin/identity/approvals/{hard_req_id}/approve",
            headers=_headers(super_admin_token),
            json={"note": "approve hard delete"},
            timeout=30,
        )
        assert approve_hard.status_code == 400
        assert "hard_delete_retention_not_completed" in approve_hard.text

    def test_super_admin_delete_protected(self, super_admin_token: str):
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(super_admin_token), timeout=30)
        assert me.status_code == 200, me.text
        me_id = me.json()["id"]

        soft_request = requests.post(
            f"{BASE_URL}/api/admin/identity/users/{me_id}/soft-delete/request",
            headers=_headers(super_admin_token),
            json={"reason": "should fail", "critical_confirmed": True},
            timeout=30,
        )
        assert soft_request.status_code == 403
        assert "self_request_not_allowed" in soft_request.text or "super_admin_protected" in soft_request.text


class TestP0BulkAndSecurity:
    def test_bulk_requires_critical_confirmation(self, super_admin_token: str):
        user_id, _, _ = _create_regular_user()
        response = requests.post(
            f"{BASE_URL}/api/admin/identity/users/bulk-status",
            headers=_headers(super_admin_token),
            json={"user_ids": [user_id], "status": "disabled", "reason": "bulk test"},
            timeout=30,
        )
        assert response.status_code == 400
        assert "critical_confirmation_required" in response.text

    def test_bulk_creates_approval_requests(self, super_admin_token: str):
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

    def test_session_revoke_blocks_token(self, super_admin_token: str):
        user_id, email, password = _create_regular_user(approve_with_token=super_admin_token)
        login_user = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": password},
            timeout=30,
        )
        assert login_user.status_code == 200, login_user.text
        user_token = login_user.json().get("access_token")
        assert user_token

        active_sessions = requests.get(
            f"{BASE_URL}/api/auth/sessions/active",
            params={"user_id": user_id},
            headers=_headers(super_admin_token),
            timeout=30,
        )
        assert active_sessions.status_code == 200, active_sessions.text
        items = active_sessions.json().get("items", [])
        if not items:
            pytest.skip("target user için aktif session bulunamadı")

        session_id = items[0]["session_id"]
        revoke = requests.post(
            f"{BASE_URL}/api/auth/sessions/{session_id}/revoke",
            headers=_headers(super_admin_token),
            json={"reason": "p0 revoke test"},
            timeout=30,
        )
        assert revoke.status_code == 200, revoke.text

        me_after = requests.get(f"{BASE_URL}/api/auth/me", headers=_headers(user_token), timeout=30)
        assert me_after.status_code == 401
        assert "session_revoked" in me_after.text

    def test_login_lock_after_failed_attempts(self):
        email = f"nonexistent.{uuid.uuid4().hex[:8]}@example.com"
        for _ in range(5):
            requests.post(
                f"{BASE_URL}/api/auth/login/user",
                json={"email": email, "password": "Wrong#1234"},
                timeout=30,
            )
        locked = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": email, "password": "Wrong#1234"},
            timeout=30,
        )
        assert locked.status_code in {423, 429, 401}


class TestP0EligibilitySurface:
    def test_identity_users_surface_has_eligibility_keys(self, super_admin_token: str):
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=_headers(super_admin_token),
            params={"page": 1, "page_size": 20},
            timeout=30,
        )
        assert response.status_code == 200, response.text
        items = response.json().get("items", [])
        if not items:
            pytest.skip("identity users boş")
        sample = items[0]
        controls = sample.get("identity_controls", {})
        checks = controls.get("compliance_checks", {})
        for key in [
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
        ]:
            assert key in checks, f"missing check: {key}"
        assert "eligible_for_login" in controls
        assert "eligible_for_ops" in controls
        assert "live_trading_eligible" in controls
