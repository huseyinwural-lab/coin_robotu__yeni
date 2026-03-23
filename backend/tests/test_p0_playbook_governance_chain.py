"""
P0 Playbook Governance Chain Tests
==================================
Tests for:
1. POST /api/admin-phase3/incident-snapshots/playbook/preview - P0 bug fix (was 500, now 200)
2. Safe execution chain: preview -> apply(planned) -> approve(super_admin) -> execute
3. Role guard: admin user should get 403 on approve endpoints
4. Governance endpoints: signals/approve and signals/reject
5. Reject reason enforcement: empty/short reason returns 422
6. Export endpoint: returns 200 with snapshot headers
7. Audit effects: audit logs created for playbook actions
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://hard-guard-layer.preview.emergentagent.com"

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


class TestP0PlaybookPreviewFix:
    """P0 Bug Fix: Playbook preview endpoint should return 200 (was 500)"""

    def test_playbook_preview_returns_200(self, super_admin_token):
        """POST /api/admin-phase3/incident-snapshots/playbook/preview should return 200"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [
                    {"action": "test_action", "severity": "INFO", "reason": "test reason"}
                ],
                "anomaly_notes": ["test note"],
                "scope": {"chain_id": "pytest_chain_001"},
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "success"
        assert data.get("message") == "playbook_preview_ready"
        assert "preview_token" in data
        assert "playbook_run_id" in data
        assert data.get("execution_state") == "preview"

    def test_playbook_preview_with_empty_actions(self, super_admin_token):
        """Preview with empty actions should use default action"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("preview", {}).get("steps")
        # Default action should be "keep current policy"
        assert any("keep current policy" in str(step.get("action", "")).lower() 
                   for step in data.get("preview", {}).get("steps", []))


class TestPlaybookExecutionChain:
    """Safe execution chain: preview -> apply(planned) -> approve(super_admin) -> execute"""

    def test_full_playbook_chain(self, super_admin_token):
        """Test complete playbook execution chain"""
        # Step 1: Preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [
                    {"action": "chain_test_action", "severity": "WARNING", "reason": "chain test"}
                ],
                "anomaly_notes": ["chain test note"],
                "scope": {"chain_id": "pytest_full_chain"},
            },
        )
        assert preview_response.status_code == 200
        preview_data = preview_response.json()
        preview_token = preview_data.get("preview_token")
        playbook_run_id = preview_data.get("playbook_run_id")
        assert preview_token
        assert playbook_run_id
        assert preview_data.get("execution_state") == "preview"

        # Step 2: Apply (planned)
        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "pytest apply reason",
            },
        )
        assert apply_response.status_code == 200
        apply_data = apply_response.json()
        assert apply_data.get("result", {}).get("execution_state") == "planned"

        # Step 3: Approve (super_admin only)
        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "pytest approve reason",
            },
        )
        assert approve_response.status_code == 200
        approve_data = approve_response.json()
        assert approve_data.get("execution_state") == "approved"

        # Step 4: Execute
        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "playbook_run_id": playbook_run_id,
                "confirm": True,
                "reason": "pytest execute reason",
            },
        )
        assert execute_response.status_code == 200
        execute_data = execute_response.json()
        assert execute_data.get("execution_state") == "executed"
        assert execute_data.get("rollback_state") == "rollback_available"

    def test_apply_requires_confirm(self, super_admin_token):
        """Apply without confirm should return 422"""
        # First create a preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "test", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        preview_token = preview_response.json().get("preview_token")

        # Try apply without confirm
        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": False,
                "reason": "test reason",
            },
        )
        assert apply_response.status_code == 422
        assert "confirm_required" in apply_response.text


class TestRoleGuard:
    """Role guard: admin user should get 403 on approve endpoints"""

    def test_admin_cannot_approve_signals(self, admin_token):
        """Admin (non-super) should get 403 on signals/approve"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/signals/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"signal_id": "test_signal", "reason": "test reason"},
        )
        assert response.status_code == 403
        assert "super_admin" in response.text.lower()

    def test_admin_cannot_approve_playbook(self, admin_token):
        """Admin (non-super) should get 403 on playbook/approve"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "playbook_run_id": "test_run_id",
                "confirm": True,
                "reason": "test reason",
            },
        )
        assert response.status_code == 403
        assert "super admin required" in response.text.lower()

    def test_admin_cannot_reject_signals(self, admin_token):
        """Admin (non-super) should get 403 on signals/reject"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/signals/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"signal_id": "test_signal", "reason": "test reason"},
        )
        assert response.status_code == 403
        assert "super_admin" in response.text.lower()

    def test_admin_cannot_apply_playbook(self, super_admin_token, admin_token):
        """Admin (non-super) should get 403 on playbook/apply"""
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_apply_test", "severity": "WARNING", "reason": "rbac"}],
                "anomaly_notes": ["rbac"],
                "scope": {"chain_id": "rbac_apply_chain"},
            },
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json().get("preview_token")

        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "admin apply denemesi",
            },
        )
        assert response.status_code == 403
        assert "super admin required" in response.text.lower()

    def test_admin_cannot_execute_playbook(self, super_admin_token, admin_token):
        """Admin (non-super) should get 403 on playbook/execute even after approve"""
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_execute_test", "severity": "WARNING", "reason": "rbac"}],
                "anomaly_notes": ["rbac"],
                "scope": {"chain_id": "rbac_execute_chain"},
            },
        )
        assert preview_response.status_code == 200
        run_id = preview_response.json().get("playbook_run_id")

        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": run_id, "confirm": True, "reason": "rbac approve"},
        )
        assert approve_response.status_code == 200

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"playbook_run_id": run_id, "confirm": True, "reason": "admin execute denemesi"},
        )
        assert execute_response.status_code == 403
        assert "super admin required" in execute_response.text.lower()

    def test_super_admin_can_apply_and_execute_playbook(self, super_admin_token):
        """Super admin should still be able to apply and execute"""
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "rbac_super_ok", "severity": "INFO", "reason": "rbac"}],
                "anomaly_notes": ["rbac super"],
                "scope": {"chain_id": "rbac_super_chain"},
            },
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json().get("preview_token")
        run_id = preview_response.json().get("playbook_run_id")

        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"preview_token": preview_token, "confirm": True, "reason": "super apply"},
        )
        assert apply_response.status_code == 200

        approve_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": run_id, "confirm": True, "reason": "super approve"},
        )
        assert approve_response.status_code == 200

        execute_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/playbook/execute",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"playbook_run_id": run_id, "confirm": True, "reason": "super execute"},
        )
        assert execute_response.status_code == 200


class TestRejectReasonEnforcement:
    """Reject reason enforcement: empty/short reason returns 422"""

    def test_reject_empty_reason_returns_422(self, super_admin_token):
        """Empty reason should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/signals/reject",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"signal_id": "test_signal", "reason": ""},
        )
        assert response.status_code == 422
        assert "string_too_short" in response.text.lower() or "min_length" in response.text.lower()

    def test_reject_short_reason_returns_422(self, super_admin_token):
        """Reason < 3 chars should return 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/signals/reject",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"signal_id": "test_signal", "reason": "ab"},
        )
        assert response.status_code == 422
        assert "string_too_short" in response.text.lower() or "min_length" in response.text.lower()

    def test_playbook_apply_short_reason_returns_422(self, super_admin_token):
        """Playbook apply with short reason should return 422"""
        # First create a preview
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "test", "severity": "INFO", "reason": "test"}],
                "anomaly_notes": [],
                "scope": {},
            },
        )
        preview_token = preview_response.json().get("preview_token")

        # Try apply with short reason
        apply_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/apply",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "preview_token": preview_token,
                "confirm": True,
                "reason": "ab",
            },
        )
        assert apply_response.status_code == 422


class TestExportEndpoint:
    """Export endpoint: returns 200 with snapshot headers"""

    def test_export_returns_200_with_headers(self, super_admin_token):
        """Export should return 200 with snapshot headers"""
        response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/export",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"correlation_id": "pytest_export_001"},
        )
        assert response.status_code == 200
        
        # Check snapshot headers
        assert "x-incident-snapshot-at" in response.headers
        assert "x-incident-snapshot-filters" in response.headers
        assert "x-incident-snapshot-row-count" in response.headers


class TestGovernanceEndpoints:
    """Governance endpoints: signals/approve and signals/reject"""

    def test_signals_approve_with_nonexistent_signal(self, super_admin_token):
        """Approve non-existent signal should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/signals/approve",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"signal_id": "nonexistent_signal_id", "reason": "test reason"},
        )
        assert response.status_code == 404
        assert "signal_not_found" in response.text

    def test_signals_reject_with_nonexistent_signal(self, super_admin_token):
        """Reject non-existent signal should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/admin/strategy/signals/reject",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={"signal_id": "nonexistent_signal_id", "reason": "test reason"},
        )
        assert response.status_code == 404
        assert "signal_not_found" in response.text


class TestAuditEffects:
    """Audit effects: audit logs created for playbook actions"""

    def test_audit_log_contains_playbook_actions(self, super_admin_token):
        """Audit log should contain playbook action entries"""
        # First create a playbook preview to generate audit entry
        requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "audit_test", "severity": "INFO", "reason": "audit test"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "pytest_audit_test"},
            },
        )

        # Check audit log
        response = requests.get(
            f"{BASE_URL}/api/admin/strategy/audit-log?limit=50",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify audit entries exist
        assert "items" in data
        assert len(data["items"]) > 0
        
        # Check for playbook-related audit actions
        actions = [item.get("action", "") for item in data["items"]]
        # At minimum, we should have some strategy-related audit entries
        assert any("strategy" in action.lower() or "playbook" in action.lower() or "signal" in action.lower() 
                   for action in actions)


class TestPlaybookRunDetail:
    """Test playbook run detail endpoint"""

    def test_get_playbook_run_detail(self, super_admin_token):
        """Get playbook run detail should return run info"""
        # First create a playbook
        preview_response = requests.post(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/preview",
            headers={"Authorization": f"Bearer {super_admin_token}"},
            json={
                "recommended_actions": [{"action": "detail_test", "severity": "INFO", "reason": "detail test"}],
                "anomaly_notes": [],
                "scope": {"chain_id": "pytest_detail_test"},
            },
        )
        playbook_run_id = preview_response.json().get("playbook_run_id")

        # Get detail
        detail_response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/runs/{playbook_run_id}",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert detail_response.status_code == 200
        data = detail_response.json()
        assert "playbook_run" in data
        assert data["playbook_run"]["id"] == playbook_run_id
        assert data["playbook_run"]["execution_state"] == "preview"

    def test_get_nonexistent_playbook_run(self, super_admin_token):
        """Get non-existent playbook run should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/admin-phase3/incident-snapshots/playbook/runs/nonexistent_run_id",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert response.status_code == 404
        assert "playbook_run_not_found" in response.text
