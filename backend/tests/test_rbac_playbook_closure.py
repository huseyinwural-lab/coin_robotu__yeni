"""
RBAC Playbook Closure Tests
============================
Tests for RBAC enforcement on playbook endpoints:
- admin token: apply/approve/execute => 403 + "Super admin required"
- super_admin: apply/approve/execute => success
- UI bypass scenario: direct endpoint calls blocked for admin
- Regression: preview/retry/rollback flows not broken
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://identity-control-1.preview.emergentagent.com"

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
ADMIN_EMAIL = "canary.requester@platform.local"
ADMIN_PASSWORD = "CanaryRequester123!"


@pytest.fixture(scope="module")
def super_admin_token():
    """Get super admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Super admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin (non-super) authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


class TestAdminBlockedOnApply:
    """Admin token should get 403 on playbook/apply"""

    def test_admin_apply_blocked_403(self, super_admin_token, admin_token):
        """Admin cannot apply playbook - returns 403 with 'Super admin required'"""
        # First create a preview with super_admin
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_apply_test", "severity": "WARNING", "reason": "rbac test"}],
                "anomaly_notes": ["rbac test"],
                "scope": {"chain_id": "rbac_apply_test_chain"},
            },
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json().get("preview_token")
        assert preview_token

        # Admin tries to apply - should get 403
        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "admin apply attempt",
            },
        )
        assert apply_response.status_code == 403, f"Expected 403, got {apply_response.status_code}: {apply_response.text}"
        assert "super admin required" in apply_response.text.lower(), f"Expected 'Super admin required' in response: {apply_response.text}"


class TestAdminBlockedOnApprove:
    """Admin token should get 403 on playbook/approve"""

    def test_admin_approve_blocked_403(self, super_admin_token, admin_token):
        """Admin cannot approve playbook - returns 403 with 'Super admin required'"""
        # Create preview with super_admin
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_approve_test", "severity": "INFO", "reason": "rbac test"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "rbac_approve_test_chain"},
            },
        )
        assert preview_response.status_code == 200
        playbook_run_id = preview_response.json().get("playbook_run_id")
        assert playbook_run_id

        # Admin tries to approve - should get 403
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "admin approve attempt",
            },
        )
        assert approve_response.status_code == 403, f"Expected 403, got {approve_response.status_code}: {approve_response.text}"
        assert "super admin required" in approve_response.text.lower(), f"Expected 'Super admin required' in response: {approve_response.text}"

    def test_admin_approve_via_alternate_route_blocked(self, super_admin_token, admin_token):
        """Admin cannot approve via /api/admin-phase3/playbook/approve route"""
        # Create preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_alt_approve", "severity": "INFO", "reason": "rbac"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        playbook_run_id = preview_response.json().get("playbook_run_id")

        # Admin tries alternate route
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "admin alt approve",
            },
        )
        assert approve_response.status_code == 403
        assert "super admin required" in approve_response.text.lower()


class TestAdminBlockedOnExecute:
    """Admin token should get 403 on playbook/execute"""

    def test_admin_execute_blocked_403(self, super_admin_token, admin_token):
        """Admin cannot execute playbook - returns 403 with 'Super admin required'"""
        # Create and approve playbook with super_admin
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_execute_test", "severity": "INFO", "reason": "rbac test"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "rbac_execute_test_chain"},
            },
        )
        assert preview_response.status_code == 200
        playbook_run_id = preview_response.json().get("playbook_run_id")

        # Approve with super_admin
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "super admin approve",
            },
        )
        assert approve_response.status_code == 200

        # Admin tries to execute - should get 403
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/execute",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "admin execute attempt",
            },
        )
        assert execute_response.status_code == 403, f"Expected 403, got {execute_response.status_code}: {execute_response.text}"
        assert "super admin required" in execute_response.text.lower(), f"Expected 'Super admin required' in response: {execute_response.text}"

    def test_admin_execute_via_alternate_route_blocked(self, super_admin_token, admin_token):
        """Admin cannot execute via /api/admin-phase3/playbook/execute route"""
        # Create and approve
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_alt_execute", "severity": "INFO", "reason": "rbac"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        playbook_run_id = preview_response.json().get("playbook_run_id")

        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": playbook_run_id, "confirm": True, "reason": "approve"},
        )

        # Admin tries alternate route
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "admin alt execute",
            },
        )
        assert execute_response.status_code == 403
        assert "super admin required" in execute_response.text.lower()


class TestSuperAdminCanApplyApproveExecute:
    """Super admin should be able to apply/approve/execute successfully"""

    def test_super_admin_full_chain_success(self, super_admin_token):
        """Super admin can complete full playbook chain"""
        # Preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "super_admin_chain", "severity": "INFO", "reason": "super admin test"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "super_admin_full_chain"},
            },
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json().get("preview_token")
        playbook_run_id = preview_response.json().get("playbook_run_id")

        # Apply
        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "super admin apply",
            },
        )
        assert apply_response.status_code == 200, f"Apply failed: {apply_response.text}"

        # Approve
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "super admin approve",
            },
        )
        assert approve_response.status_code == 200, f"Approve failed: {approve_response.text}"

        # Execute
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "super admin execute",
            },
        )
        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        assert execute_response.json().get("execution_state") == "executed"


class TestUIBypassScenario:
    """Direct endpoint calls should be blocked for admin (UI bypass prevention)"""

    def test_direct_apply_call_blocked_for_admin(self, super_admin_token, admin_token):
        """Direct API call to apply is blocked for admin user"""
        # Create preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "ui_bypass_test", "severity": "INFO", "reason": "bypass test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        preview_token = preview_response.json().get("preview_token")

        # Direct call from admin - should be blocked
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "ui bypass attempt",
            },
        )
        assert response.status_code == 403
        assert "super admin required" in response.text.lower()


class TestRegressionPreviewRetryRollback:
    """Regression: preview/retry/rollback flows should not be broken"""

    def test_preview_still_works(self, super_admin_token):
        """Preview endpoint still works for super_admin"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "regression_preview", "severity": "INFO", "reason": "regression"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        assert response.status_code == 200
        assert response.json().get("message") == "playbook_preview_ready"

    def test_preview_works_for_admin(self, admin_token):
        """Preview endpoint works for admin (view only)"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "recommended_actions": [{"action": "admin_preview", "severity": "INFO", "reason": "admin preview"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        assert response.status_code == 200
        assert response.json().get("message") == "playbook_preview_ready"

    def test_rollback_works_for_super_admin(self, super_admin_token):
        """Rollback works for super_admin after execute"""
        # Full chain to executed state
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rollback_test", "severity": "INFO", "reason": "rollback test"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "rollback_regression_chain"},
            },
        )
        preview_token = preview_response.json().get("preview_token")
        playbook_run_id = preview_response.json().get("playbook_run_id")

        # Apply
        requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"preview_token": preview_token, "confirm": True, "reason": "apply"},
        )

        # Approve
        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": playbook_run_id, "confirm": True, "reason": "approve"},
        )

        # Execute
        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": playbook_run_id, "confirm": True, "reason": "execute"},
        )

        # Rollback
        rollback_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/rollback",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "rollback test",
            },
        )
        assert rollback_response.status_code == 200
        assert rollback_response.json().get("execution_state") == "rollback_executed"

    def test_retry_works_for_super_admin(self, super_admin_token):
        """Retry works for super_admin on failed playbook"""
        # Create a playbook that will fail (using fail action)
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "fail_action", "severity": "INFO", "reason": "force fail"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "retry_regression_chain"},
            },
        )
        preview_token = preview_response.json().get("preview_token")
        playbook_run_id = preview_response.json().get("playbook_run_id")

        # Apply
        requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"preview_token": preview_token, "confirm": True, "reason": "apply"},
        )

        # Approve
        requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": playbook_run_id, "confirm": True, "reason": "approve"},
        )

        # Execute (will fail due to fail_action)
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": playbook_run_id, "confirm": True, "reason": "execute"},
        )
        # Should be failed state
        assert execute_response.json().get("execution_state") == "failed"

        # Retry
        retry_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/retry",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "original_playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "retry test",
            },
        )
        assert retry_response.status_code == 200
        assert retry_response.json().get("message") == "playbook_retry_created"


class TestPreflightRoleGate:
    """Preflight endpoint should return role_gate info"""

    def test_preflight_returns_role_gate(self, super_admin_token):
        """Preflight should include role_gate with current_role and permissions"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "role_gate" in data
        assert data["role_gate"]["current_role"] == "super_admin"
        assert data["role_gate"]["approve_allowed"] is True
        assert data["role_gate"]["apply_allowed"] is True
        assert data["role_gate"]["execute_allowed"] is True

    def test_preflight_admin_role_gate(self, admin_token):
        """Preflight for admin should show restricted permissions"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preflight",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "role_gate" in data
        assert data["role_gate"]["current_role"] == "admin"
        assert data["role_gate"]["approve_allowed"] is False
        assert data["role_gate"]["apply_allowed"] is False
        assert data["role_gate"]["execute_allowed"] is False
