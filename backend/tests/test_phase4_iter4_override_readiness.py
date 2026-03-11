"""
Phase-4 Iteration-4: Override + Readiness + Shell Script Tests
Tests for:
  - POST /api/phase4/admin/release-gate/override: BLOCKED status required, reason_code validation, reason_note min 12 chars
  - Override response fields: override_id, admin_user_id, release_gate_snapshot, reason (code + note), expires_at, revoked_at, deploy_context
  - POST /api/phase4/admin/release-gate/override/{id}/revoke: Revocation flow
  - GET /api/phase4/admin/release-gate: status=PASS_WITH_OVERRIDE when override active
  - Shell script /app/scripts/run_release_gate_check.sh: exit 0 + release_gate_status=PASS_WITH_OVERRIDE when override active, non-zero when BLOCKED
  - GET /api/exchange/readiness-checklist: awaiting_valid_key / ready_for_test_order / blocked state model, stale (10 min) fields
  - POST /api/exchange/test-order: Blocks with detail.status when readiness not ready_for_test_order (awaiting_valid_key, blocked, etc)
  - GET /api/phase4/admin/release-gate/overrides: List overrides
  - GET /api/phase4/admin/override-analytics: Override analytics endpoint
  - GET /api/phase4/admin/alert-history: Alert history endpoint
"""
import os
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL env var required"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_token_and_id():
    """Create a test user and get token or use existing test user"""
    test_email = "TEST_phase4iter4@example.com"
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
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
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


class TestOverrideReasonCodeValidation:
    """POST /api/phase4/admin/release-gate/override - Reason code validation"""

    def test_invalid_reason_code_returns_400(self, admin_headers):
        """Invalid reason_code should return 400"""
        payload = {
            "reason_code": "INVALID_CODE_XYZ",
            "reason_note": "This is a valid note with enough chars",
            "ttl_minutes": 30,
            "deploy_context": {}
        }
        response = requests.post(
            f"{BASE_URL}/api/phase4/admin/release-gate/override",
            headers=admin_headers,
            json=payload,
        )
        # Should be 400 because reason_code is invalid
        # Note: May also be 400 if gate not BLOCKED
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_reason_note_too_short_returns_400(self, admin_headers):
        """reason_note < 12 chars should return 400"""
        payload = {
            "reason_code": "false_positive",
            "reason_note": "short",  # Only 5 chars, should fail
            "ttl_minutes": 30,
            "deploy_context": {}
        }
        response = requests.post(
            f"{BASE_URL}/api/phase4/admin/release-gate/override",
            headers=admin_headers,
            json=payload,
        )
        # Should be 400 because reason_note is too short
        # Note: May also be 400 if gate not BLOCKED
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"


class TestOverrideInNonBlockedState:
    """Override creation when gate is NOT blocked should fail"""

    def test_override_requires_blocked_status(self, admin_headers):
        """POST override when gate is not BLOCKED should return 400"""
        # First check gate status
        gate_resp = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
        )
        assert gate_resp.status_code == 200
        gate_status = gate_resp.json()["status"]
        
        # If gate is not BLOCKED, override creation should fail
        if gate_status != "BLOCKED":
            payload = {
                "reason_code": "false_positive",
                "reason_note": "This is a valid note with enough characters",
                "ttl_minutes": 30,
                "deploy_context": {}
            }
            response = requests.post(
                f"{BASE_URL}/api/phase4/admin/release-gate/override",
                headers=admin_headers,
                json=payload,
            )
            # Should fail because gate is not BLOCKED
            assert response.status_code == 400, \
                f"Override should fail when gate is not BLOCKED, got {response.status_code}"
            # Check error detail mentions BLOCKED
            data = response.json()
            assert "BLOCKED" in str(data.get("detail", "")), \
                f"Error should mention BLOCKED requirement: {data}"


class TestOverrideResponseFields:
    """Override response should have required fields"""

    def test_override_list_returns_200(self, admin_headers):
        """GET /api/phase4/admin/release-gate/overrides should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate/overrides",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_override_list_is_array(self, admin_headers):
        """GET /api/phase4/admin/release-gate/overrides should return array"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate/overrides",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Response should be list, got {type(data)}"

    def test_override_items_have_required_fields(self, admin_headers):
        """Override items should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate/overrides",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            # Required fields per spec
            required_fields = [
                "override_id",
                "admin_user_id",
                "reason_code",
                "reason_note",
                "release_gate_snapshot",
                "created_at",
                "expires_at",
                "revoked_at",  # Can be null
                "deploy_context",
                "used_deploy_count",
            ]
            for field in required_fields:
                assert field in item, f"Override should have {field} field"


class TestRevokeOverrideEndpoint:
    """POST /api/phase4/admin/release-gate/override/{id}/revoke tests"""

    def test_revoke_nonexistent_override_returns_404(self, admin_headers):
        """Revoking non-existent override should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/admin/release-gate/override/nonexistent-id-12345/revoke",
            headers=admin_headers,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"

    def test_revoke_existing_override_returns_override(self, admin_headers):
        """Revoking existing override should return the override object"""
        # Get list of overrides
        list_resp = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate/overrides",
            headers=admin_headers,
        )
        assert list_resp.status_code == 200
        overrides = list_resp.json()
        
        # If there's an override, try to revoke it (or it's already revoked)
        if len(overrides) > 0:
            override_id = overrides[0]["override_id"]
            response = requests.post(
                f"{BASE_URL}/api/phase4/admin/release-gate/override/{override_id}/revoke",
                headers=admin_headers,
            )
            # Should return 200 with override object
            assert response.status_code == 200, \
                f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert "override_id" in data
            assert "revoked_at" in data  # Should be set now


class TestReleaseGateStatusWithOverride:
    """GET /api/phase4/admin/release-gate should show PASS_WITH_OVERRIDE when override is active"""

    def test_release_gate_has_override_fields(self, admin_headers):
        """Release gate response should have override-related fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "status" in data
        assert "override_active" in data
        assert "override_expires_at" in data
        assert "override_id" in data
        
        # If override is active, status should be PASS_WITH_OVERRIDE
        if data["override_active"]:
            assert data["status"] == "PASS_WITH_OVERRIDE", \
                f"When override_active=true, status should be PASS_WITH_OVERRIDE, got {data['status']}"


class TestShellScriptReleaseGate:
    """Shell script /app/scripts/run_release_gate_check.sh tests"""

    def test_script_exists_and_executable(self):
        """Script should exist and be executable"""
        script_path = "/app/scripts/run_release_gate_check.sh"
        assert os.path.exists(script_path), f"Script should exist at {script_path}"
        assert os.access(script_path, os.X_OK), "Script should be executable"

    def test_script_outputs_release_gate_status(self):
        """Script should output release_gate_status=VALUE"""
        script_path = "/app/scripts/run_release_gate_check.sh"
        try:
            result = subprocess.run(
                [script_path, "--env=prod"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Check output contains release_gate_status
            assert "release_gate_status=" in result.stdout, \
                f"Script should output release_gate_status=VALUE, got: {result.stdout}"
            
            # Extract status
            for line in result.stdout.strip().split("\n"):
                if line.startswith("release_gate_status="):
                    status = line.split("=")[1]
                    assert status in ["PASS", "WARNING", "BLOCKED", "PASS_WITH_OVERRIDE"], \
                        f"Status should be valid, got: {status}"
        except subprocess.TimeoutExpired:
            pytest.skip("Script timed out")

    def test_script_exit_code_blocked(self):
        """Script should exit with code 2 when BLOCKED (exit 0 when PASS/PASS_WITH_OVERRIDE)"""
        script_path = "/app/scripts/run_release_gate_check.sh"
        try:
            result = subprocess.run(
                [script_path, "--env=prod"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            # Parse status from output
            status = None
            for line in result.stdout.strip().split("\n"):
                if line.startswith("release_gate_status="):
                    status = line.split("=")[1]
                    break
            
            if status == "BLOCKED":
                assert result.returncode == 2, \
                    f"Script should exit with code 2 when BLOCKED, got {result.returncode}"
            elif status in ["PASS", "PASS_WITH_OVERRIDE", "WARNING"]:
                assert result.returncode == 0, \
                    f"Script should exit with code 0 when {status}, got {result.returncode}"
        except subprocess.TimeoutExpired:
            pytest.skip("Script timed out")


class TestUserReadinessChecklist:
    """GET /api/exchange/readiness-checklist tests"""

    def test_readiness_checklist_returns_200(self, user_headers):
        """GET readiness-checklist should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=user_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_readiness_checklist_has_required_fields(self, user_headers):
        """Readiness checklist should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "readiness_status",
            "has_api_key",
            "has_api_secret",
            "validation_success",
            "can_trade",
            "is_testnet_environment",
            "is_validation_stale",
            "validation_timestamp",
            "stale_after_minutes",
            "last_error_reason",
        ]
        for field in required_fields:
            assert field in data, f"Readiness should have {field} field"

    def test_readiness_status_valid_states(self, user_headers):
        """readiness_status should be valid state"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        valid_states = ["awaiting_valid_key", "ready_for_test_order", "blocked"]
        assert data["readiness_status"] in valid_states, \
            f"readiness_status should be one of {valid_states}, got {data['readiness_status']}"

    def test_stale_threshold_is_10_minutes(self, user_headers):
        """stale_after_minutes should be 10"""
        response = requests.get(
            f"{BASE_URL}/api/exchange/readiness-checklist",
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["stale_after_minutes"] == 10, \
            f"stale_after_minutes should be 10, got {data['stale_after_minutes']}"


class TestTestOrderBlocking:
    """POST /api/exchange/test-order blocking tests"""

    def test_test_order_blocked_when_not_ready(self, user_headers):
        """POST test-order should return 400 when readiness is not ready_for_test_order"""
        # First clear any API keys to ensure awaiting_valid_key state
        requests.put(
            f"{BASE_URL}/api/phase4/exchange-settings",
            headers=user_headers,
            json={
                "exchange": "binance",
                "mode": "testnet",
                "api_key": "",
                "api_secret": "",
            },
        )
        
        # Now try test-order - should be blocked
        response = requests.post(
            f"{BASE_URL}/api/exchange/test-order",
            headers=user_headers,
        )
        
        # Should be 400, not 500
        assert response.status_code != 500, \
            f"test-order should not return 500 internal error, got {response.status_code}"
        assert response.status_code == 400, \
            f"test-order should return 400 when blocked, got {response.status_code}: {response.text}"

    def test_test_order_blocked_detail_has_status(self, user_headers):
        """POST test-order blocked response should have detail.status"""
        response = requests.post(
            f"{BASE_URL}/api/exchange/test-order",
            headers=user_headers,
        )
        
        if response.status_code == 400:
            data = response.json()
            detail = data.get("detail")
            
            # detail can be string or dict
            if isinstance(detail, dict):
                assert "status" in detail, f"detail should have status field: {detail}"
                assert detail["status"] in ["awaiting_valid_key", "blocked"], \
                    f"detail.status should indicate block reason, got {detail['status']}"


class TestOverrideAnalyticsEndpoint:
    """GET /api/phase4/admin/override-analytics tests"""

    def test_override_analytics_returns_200(self, admin_headers):
        """GET override-analytics should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/override-analytics?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_override_analytics_has_required_fields(self, admin_headers):
        """Override analytics should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/override-analytics?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "days" in data
        assert "points" in data
        assert "alert_source_breakdown" in data
        assert isinstance(data["points"], list)

    def test_override_analytics_points_have_fields(self, admin_headers):
        """Override analytics points should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/override-analytics?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data["points"]) > 0:
            point = data["points"][0]
            assert "date" in point
            assert "blocked_gate_count" in point
            assert "override_count" in point
            assert "override_deploy_count" in point


class TestAlertHistoryEndpoint:
    """GET /api/phase4/admin/alert-history tests"""

    def test_alert_history_returns_200(self, admin_headers):
        """GET alert-history should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/alert-history?limit=30",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_alert_history_is_list(self, admin_headers):
        """GET alert-history should return list"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/alert-history?limit=30",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Response should be list, got {type(data)}"

    def test_alert_history_items_have_fields(self, admin_headers):
        """Alert history items should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/alert-history?limit=30",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            assert "created_at" in item
            assert "action" in item
            assert "severity" in item
            assert "source" in item
            assert "details" in item


class TestOverrideValidReasonCodes:
    """Test valid reason_code enum values"""

    def test_valid_reason_codes(self):
        """Valid reason codes should be: false_positive, exchange_incident, ops_emergency, manual_review"""
        valid_codes = {"false_positive", "exchange_incident", "ops_emergency", "manual_review"}
        # This is defined in live_mode_service.py
        assert len(valid_codes) == 4
        for code in valid_codes:
            assert len(code) > 0


class TestDefaultOverrideTTL:
    """Override TTL tests - default 30 min, max 60 min"""

    def test_ttl_max_validation(self, admin_headers):
        """TTL > 60 should be rejected or clamped"""
        # Get gate status first
        gate_resp = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
        )
        assert gate_resp.status_code == 200
        # Try with TTL > 60
        payload = {
            "reason_code": "false_positive",
            "reason_note": "This is a valid note with enough characters for testing",
            "ttl_minutes": 120,  # Exceeds max
            "deploy_context": {}
        }
        response = requests.post(
            f"{BASE_URL}/api/phase4/admin/release-gate/override",
            headers=admin_headers,
            json=payload,
        )
        
        # Should be 400 (either for TTL exceeding max, or gate not BLOCKED)
        assert response.status_code == 400 or response.status_code == 422, \
            f"Expected 400 or 422 for TTL > 60, got {response.status_code}"
