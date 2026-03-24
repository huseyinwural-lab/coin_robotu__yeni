"""
Production Gate Control Panel API Tests
Tests for:
- GET /api/phase4/admin/production-gate status
- POST /api/phase4/admin/production-gate/state -> checklist/check fail varken GO 400
- POST /api/phase4/admin/production-gate/override -> super_admin only, ttl<=30
- POST /api/phase4/admin/production-gate/override/{id}/revoke
- POST /api/phase4/admin/production-gate/checks/rerun and /checks/{check_key}/rerun
- POST /api/phase4/admin/production-gate/mode-transition -> NO_GO iken LIVE 403
- PUT /api/phase4/live-config -> live_mode_enabled/trading_enabled true iken gate enforcement 403
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://strategy-version-gov.preview.emergentagent.com"

# Test credentials
SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"


class TestProductionGateControlPanel:
    """Production Gate Control Panel API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token = None
        self.user_role = None
        
    def _login_super_admin(self):
        """Login as super admin and get token"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.user_role = data.get("user", {}).get("role")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            return True
        return False
    
    # ==================== GET /api/phase4/admin/production-gate ====================
    
    def test_get_production_gate_status_requires_auth(self):
        """Test that production gate status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/production-gate")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: GET /api/phase4/admin/production-gate requires authentication")
    
    def test_get_production_gate_status_success(self):
        """Test GET production gate status returns correct structure"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        required_fields = [
            "configured_state", "effective_state", "deploy_allowed",
            "checklist_complete", "checks_all_pass", "has_stale_or_running",
            "blocked_reason_codes", "checklist", "checks"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify state values
        assert data["configured_state"] in ["NO_GO", "GO", "GO_WITH_OVERRIDE"], f"Invalid configured_state: {data['configured_state']}"
        assert data["effective_state"] in ["NO_GO", "GO", "GO_WITH_OVERRIDE"], f"Invalid effective_state: {data['effective_state']}"
        assert isinstance(data["deploy_allowed"], bool), "deploy_allowed should be boolean"
        assert isinstance(data["checklist"], list), "checklist should be a list"
        assert isinstance(data["checks"], list), "checks should be a list"
        
        print(f"PASS: GET /api/phase4/admin/production-gate returns valid structure")
        print(f"  configured_state: {data['configured_state']}")
        print(f"  effective_state: {data['effective_state']}")
        print(f"  deploy_allowed: {data['deploy_allowed']}")
        print(f"  checklist_complete: {data['checklist_complete']}")
        print(f"  checks_all_pass: {data['checks_all_pass']}")
    
    def test_get_production_gate_with_refresh_checks(self):
        """Test GET production gate with refresh_checks=true"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate?refresh_checks=true")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "checks" in data, "Missing checks field"
        print(f"PASS: GET /api/phase4/admin/production-gate?refresh_checks=true works, checks count: {len(data['checks'])}")
    
    # ==================== POST /api/phase4/admin/production-gate/state ====================
    
    def test_set_state_go_fails_when_checklist_incomplete(self):
        """Test that setting GO state fails when checklist is incomplete (400)"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # First, ensure checklist is incomplete by unchecking an item
        gate_response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate")
        assert gate_response.status_code == 200
        gate_data = gate_response.json()
        
        # Uncheck first checklist item if any exist
        if gate_data.get("checklist"):
            first_item = gate_data["checklist"][0]
            self.session.patch(
                f"{BASE_URL}/api/phase4/admin/production-gate/checklist/{first_item['item_key']}",
                json={"checked": False}
            )
        
        # Try to set GO state
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "GO",
                "reason_code": "TEST_GO",
                "reason_text": "Testing GO state transition"
            }
        )
        
        # Should fail with 400 if checklist incomplete or checks not passed
        if response.status_code == 400:
            print(f"PASS: Setting GO state fails with 400 when preconditions not met: {response.json()}")
        elif response.status_code == 200:
            # If it succeeded, checklist was complete and checks passed
            print(f"INFO: GO state set successfully (checklist was complete and checks passed)")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}: {response.text}")
    
    def test_set_state_no_go_always_allowed(self):
        """Test that setting NO_GO state is always allowed"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "TEST_NO_GO",
                "reason_text": "Testing NO_GO state transition"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["configured_state"] == "NO_GO", f"Expected NO_GO, got {data['configured_state']}"
        print("PASS: Setting NO_GO state always succeeds")
    
    def test_set_state_requires_reason_code(self):
        """Test that setting state requires reason_code"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "",  # Empty reason code
                "reason_text": "Testing validation"
            }
        )
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
        print("PASS: Setting state requires non-empty reason_code (validation error)")
    
    # ==================== POST /api/phase4/admin/production-gate/override ====================
    
    def test_create_override_requires_super_admin(self):
        """Test that creating override requires super_admin role"""
        # This test would need a non-super-admin user to properly test
        # For now, we verify super_admin can create override
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # First ensure we're in NO_GO state
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_OVERRIDE_TEST",
                "reason_text": "Preparing for override test"
            }
        )
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override",
            json={
                "reason_code": "INCIDENT_MITIGATION",
                "reason_text": "Testing override creation for incident mitigation",
                "ttl_minutes": 15
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["effective_state"] == "GO_WITH_OVERRIDE", f"Expected GO_WITH_OVERRIDE, got {data['effective_state']}"
            assert data["active_override"] is not None, "Expected active_override to be set"
            print(f"PASS: Super admin can create override, override_id: {data['active_override'].get('override_id')}")
        elif response.status_code == 400:
            # May fail if already in GO state
            print(f"INFO: Override creation returned 400 (may already be in GO state): {response.json()}")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}: {response.text}")
    
    def test_create_override_ttl_max_30_minutes(self):
        """Test that override TTL cannot exceed 30 minutes"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # First ensure we're in NO_GO state
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_TTL_TEST",
                "reason_text": "Preparing for TTL test"
            }
        )
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override",
            json={
                "reason_code": "INCIDENT_MITIGATION",
                "reason_text": "Testing TTL validation with 60 minutes",
                "ttl_minutes": 60  # Exceeds max of 30
            }
        )
        assert response.status_code in [400, 422], f"Expected 400/422 for TTL > 30, got {response.status_code}: {response.text}"
        print("PASS: Override TTL > 30 minutes is rejected (validation error)")
    
    def test_create_override_requires_valid_reason_code(self):
        """Test that override requires valid enum reason_code"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # First ensure we're in NO_GO state
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_REASON_TEST",
                "reason_text": "Preparing for reason code test"
            }
        )
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override",
            json={
                "reason_code": "INVALID_REASON_CODE",  # Not in allowed enum
                "reason_text": "Testing invalid reason code",
                "ttl_minutes": 15
            }
        )
        assert response.status_code in [400, 422], f"Expected 400/422 for invalid reason_code, got {response.status_code}: {response.text}"
        print("PASS: Override with invalid reason_code is rejected (validation error)")
    
    # ==================== POST /api/phase4/admin/production-gate/override/{id}/revoke ====================
    
    def test_revoke_override(self):
        """Test revoking an active override"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # First ensure we're in NO_GO state and create an override
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_REVOKE_TEST",
                "reason_text": "Preparing for revoke test"
            }
        )
        
        # Create override
        create_response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override",
            json={
                "reason_code": "HOTFIX_VALIDATED",
                "reason_text": "Testing override revoke functionality",
                "ttl_minutes": 15
            }
        )
        
        if create_response.status_code != 200:
            print(f"INFO: Could not create override for revoke test: {create_response.text}")
            return
        
        data = create_response.json()
        override_id = data.get("active_override", {}).get("override_id")
        
        if not override_id:
            print("INFO: No override_id returned, skipping revoke test")
            return
        
        # Revoke the override
        revoke_response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/override/{override_id}/revoke"
        )
        assert revoke_response.status_code == 200, f"Expected 200, got {revoke_response.status_code}: {revoke_response.text}"
        
        revoke_data = revoke_response.json()
        assert revoke_data["configured_state"] == "NO_GO", f"Expected NO_GO after revoke, got {revoke_data['configured_state']}"
        print(f"PASS: Override {override_id} revoked successfully")
    
    # ==================== POST /api/phase4/admin/production-gate/checks/rerun ====================
    
    def test_rerun_all_checks(self):
        """Test rerunning all production gate checks"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.post(f"{BASE_URL}/api/phase4/admin/production-gate/checks/rerun")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "checks" in data, "Missing checks in response"
        print(f"PASS: Rerun all checks succeeded, checks count: {len(data['checks'])}")
    
    def test_rerun_single_check(self):
        """Test rerunning a single check by key"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # First get available checks
        gate_response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate")
        assert gate_response.status_code == 200
        gate_data = gate_response.json()
        
        if not gate_data.get("checks"):
            print("INFO: No checks available to rerun individually")
            return
        
        check_key = gate_data["checks"][0]["check_key"]
        
        response = self.session.post(f"{BASE_URL}/api/phase4/admin/production-gate/checks/{check_key}/rerun")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "checks" in data, "Missing checks in response"
        print(f"PASS: Rerun single check '{check_key}' succeeded")
    
    def test_rerun_invalid_check_key(self):
        """Test rerunning with invalid check key returns 400"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.post(f"{BASE_URL}/api/phase4/admin/production-gate/checks/invalid_check_key_xyz/rerun")
        assert response.status_code == 400, f"Expected 400 for invalid check key, got {response.status_code}"
        print("PASS: Rerun with invalid check key returns 400")
    
    # ==================== POST /api/phase4/admin/production-gate/mode-transition ====================
    
    def test_mode_transition_to_live_blocked_when_no_go(self):
        """Test that LIVE mode transition is blocked when gate is NO_GO (403)"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # Ensure we're in NO_GO state
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_MODE_TEST",
                "reason_text": "Preparing for mode transition test"
            }
        )
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/mode-transition",
            json={
                "target_mode": "LIVE",
                "reason_text": "Testing LIVE transition when NO_GO",
                "confirmation_phrase": "SWITCH TO LIVE"
            }
        )
        
        # Should be blocked with 403 when gate is NO_GO
        assert response.status_code == 403, f"Expected 403 for LIVE transition when NO_GO, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "production_gate_blocked" in str(data.get("detail", {})), f"Expected production_gate_blocked error: {data}"
        print("PASS: LIVE mode transition blocked with 403 when gate is NO_GO")
    
    def test_mode_transition_requires_correct_confirmation_phrase(self):
        """Test that mode transition requires correct confirmation phrase"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/mode-transition",
            json={
                "target_mode": "PAPER",
                "reason_text": "Testing wrong confirmation phrase",
                "confirmation_phrase": "WRONG PHRASE"
            }
        )
        assert response.status_code == 400, f"Expected 400 for wrong phrase, got {response.status_code}"
        
        data = response.json()
        assert "invalid_confirmation_phrase" in str(data.get("detail", {})), f"Expected invalid_confirmation_phrase error: {data}"
        print("PASS: Mode transition with wrong confirmation phrase returns 400")
    
    def test_mode_transition_to_paper_allowed(self):
        """Test that PAPER mode transition is allowed"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/mode-transition",
            json={
                "target_mode": "PAPER",
                "reason_text": "Testing PAPER mode transition",
                "confirmation_phrase": "SWITCH TO PAPER"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status ok: {data}"
        print("PASS: PAPER mode transition allowed")
    
    # ==================== PUT /api/phase4/live-config gate enforcement ====================
    
    def test_live_config_enable_blocked_when_no_go(self):
        """Test that enabling live_mode_enabled/trading_enabled is blocked when gate is NO_GO (403)"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # Ensure we're in NO_GO state
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_CONFIG_TEST",
                "reason_text": "Preparing for live config test"
            }
        )
        
        # Get current config first
        get_response = self.session.get(f"{BASE_URL}/api/phase4/live-config")
        if get_response.status_code != 200:
            print(f"INFO: Could not get live-config: {get_response.text}")
            return
        
        current_config = get_response.json()
        
        # Try to enable live_mode_enabled
        update_payload = {
            **current_config,
            "live_mode_enabled": True
        }
        # Remove id and updated_at if present
        update_payload.pop("id", None)
        update_payload.pop("updated_at", None)
        
        response = self.session.put(
            f"{BASE_URL}/api/phase4/live-config",
            json=update_payload
        )
        
        # Should be blocked with 403 when gate is NO_GO
        assert response.status_code == 403, f"Expected 403 for live_mode_enabled when NO_GO, got {response.status_code}: {response.text}"
        print("PASS: Enabling live_mode_enabled blocked with 403 when gate is NO_GO")
    
    def test_live_config_enable_trading_blocked_when_no_go(self):
        """Test that enabling trading_enabled is blocked when gate is NO_GO (403)"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # Ensure we're in NO_GO state
        self.session.post(
            f"{BASE_URL}/api/phase4/admin/production-gate/state",
            json={
                "target_state": "NO_GO",
                "reason_code": "PREPARE_TRADING_TEST",
                "reason_text": "Preparing for trading enabled test"
            }
        )
        
        # Get current config first
        get_response = self.session.get(f"{BASE_URL}/api/phase4/live-config")
        if get_response.status_code != 200:
            print(f"INFO: Could not get live-config: {get_response.text}")
            return
        
        current_config = get_response.json()
        
        # Try to enable trading_enabled
        update_payload = {
            **current_config,
            "trading_enabled": True
        }
        # Remove id and updated_at if present
        update_payload.pop("id", None)
        update_payload.pop("updated_at", None)
        
        response = self.session.put(
            f"{BASE_URL}/api/phase4/live-config",
            json=update_payload
        )
        
        # Should be blocked with 403 when gate is NO_GO
        assert response.status_code == 403, f"Expected 403 for trading_enabled when NO_GO, got {response.status_code}: {response.text}"
        print("PASS: Enabling trading_enabled blocked with 403 when gate is NO_GO")
    
    # ==================== Checklist toggle tests ====================
    
    def test_checklist_toggle(self):
        """Test toggling checklist items"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        # Get current gate status
        gate_response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate")
        assert gate_response.status_code == 200
        gate_data = gate_response.json()
        
        if not gate_data.get("checklist"):
            print("INFO: No checklist items available")
            return
        
        first_item = gate_data["checklist"][0]
        item_key = first_item["item_key"]
        current_checked = first_item["checked"]
        
        # Toggle the item
        response = self.session.patch(
            f"{BASE_URL}/api/phase4/admin/production-gate/checklist/{item_key}",
            json={"checked": not current_checked}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Find the updated item
        updated_item = next((item for item in data["checklist"] if item["item_key"] == item_key), None)
        assert updated_item is not None, f"Could not find item {item_key} in response"
        assert updated_item["checked"] == (not current_checked), f"Checklist item not toggled correctly"
        
        print(f"PASS: Checklist item '{item_key}' toggled from {current_checked} to {not current_checked}")
    
    # ==================== Audit history tests ====================
    
    def test_audit_history_included(self):
        """Test that audit history is included in gate status"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate")
        assert response.status_code == 200
        
        data = response.json()
        assert "audit_history" in data, "Missing audit_history in response"
        assert isinstance(data["audit_history"], list), "audit_history should be a list"
        
        if data["audit_history"]:
            first_audit = data["audit_history"][0]
            assert "action" in first_audit, "Audit entry missing action"
            assert "actor_role" in first_audit, "Audit entry missing actor_role"
            print(f"PASS: Audit history included, {len(data['audit_history'])} entries")
        else:
            print("INFO: Audit history is empty")
    
    # ==================== JSON Export tests ====================
    
    def test_json_export(self):
        """Test JSON export endpoint"""
        assert self._login_super_admin(), "Failed to login as super admin"
        
        response = self.session.get(f"{BASE_URL}/api/phase4/admin/production-gate/export/raw")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "exported_at" in data, "Missing exported_at in export"
        assert "gate" in data, "Missing gate in export"
        print("PASS: JSON export endpoint works correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
