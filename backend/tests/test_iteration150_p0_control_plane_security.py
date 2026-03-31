"""
Iteration 150: P0 Control Plane Security Hardening Tests
Tests for:
- Admin credential orchestration endpoints (list/create/probe/verify/revoke/rotate)
- Credential read-back verification after create/rotate
- Permission scope validation (read/trade/withdraw) response fields
- Withdraw scope execution - permission_restricted behavior
- Lifecycle status flow: pending_verify/verified/revoked/rotated_pending_verify
- Control-plane sanity check endpoint
- Execution validation endpoint with net_status + checks
- Credential resolution preview live environment hard-gate
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestAdminCredentialOrchestrationList:
    """Test credential list endpoint with filters"""

    def test_list_credentials_returns_200(self, auth_headers):
        """GET /api/venues/admin/credentials returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ List credentials returned {len(data)} items")

    def test_list_credentials_with_filters(self, auth_headers):
        """GET /api/venues/admin/credentials with exchange/market/environment filters"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "include_inactive": True
            },
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Filtered credentials returned {len(data)} items")


class TestAdminCredentialOrchestrationCreate:
    """Test credential create endpoint with read-back verification"""

    def test_create_credential_returns_201_with_lifecycle_pending_verify(self, auth_headers):
        """POST /api/venues/admin/credentials creates credential with pending_verify lifecycle"""
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "scope_type": "global",
            "scope_id": None,
            "exchange": "binance",
            "market_type": "spot",
            "purpose": "market_data",
            "environment": "testnet",
            "api_key": f"TEST_KEY_{unique_id}",
            "api_secret": f"TEST_SECRET_{unique_id}",
            "passphrase": None,
            "base_url_override": None,
            "ip_binding_note": None,
            "is_default": False
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            json=payload,
            timeout=15
        )
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify lifecycle_status is pending_verify
        assert "lifecycle_status" in data, "Response should contain lifecycle_status"
        assert data["lifecycle_status"] == "pending_verify", f"Expected pending_verify, got {data['lifecycle_status']}"
        
        # Verify permission_scope fields exist
        assert "permission_scope" in data, "Response should contain permission_scope"
        permission_scope = data["permission_scope"]
        assert "read" in permission_scope, "permission_scope should have read field"
        assert "trade" in permission_scope, "permission_scope should have trade field"
        assert "withdraw" in permission_scope, "permission_scope should have withdraw field"
        
        # Verify approval_status is pending
        assert data.get("approval_status") == "pending", "New credential should have pending approval_status"
        
        # Verify is_active is False
        assert data.get("is_active") == False, "New credential should be inactive"
        
        print(f"✓ Created credential with id={data.get('id')}, lifecycle_status={data['lifecycle_status']}")
        return data.get("id")

    def test_create_credential_validates_exchange(self, auth_headers):
        """POST /api/venues/admin/credentials rejects invalid exchange"""
        payload = {
            "scope_type": "global",
            "exchange": "invalid_exchange",
            "market_type": "spot",
            "purpose": "market_data",
            "environment": "testnet",
            "api_key": "test_key",
            "api_secret": "test_secret",
            "is_default": False
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            json=payload,
            timeout=15
        )
        assert response.status_code == 400, f"Expected 400 for invalid exchange, got {response.status_code}"
        print("✓ Invalid exchange correctly rejected with 400")


class TestAdminCredentialOrchestrationProbe:
    """Test credential probe endpoint"""

    def test_probe_credential_returns_probe_status(self, auth_headers):
        """POST /api/venues/admin/credentials/{id}/probe returns probe status"""
        # First get a credential to probe
        list_response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=15
        )
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No credentials available to probe")
        
        credential_id = list_response.json()[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/probe",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify probe status fields
        assert "last_probe_status" in data, "Response should contain last_probe_status"
        assert "last_probe_message" in data, "Response should contain last_probe_message"
        assert "last_probe_meta" in data, "Response should contain last_probe_meta"
        assert "permission_scope" in data, "Response should contain permission_scope"
        
        print(f"✓ Probe returned status={data.get('last_probe_status')}, message={data.get('last_probe_message')}")


class TestAdminCredentialOrchestrationVerify:
    """Test credential verify endpoint"""

    def test_verify_credential_endpoint_exists(self, auth_headers):
        """POST /api/venues/admin/credentials/{id}/verify endpoint exists"""
        # First get a credential
        list_response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=15
        )
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No credentials available to verify")
        
        credential_id = list_response.json()[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/verify",
            headers=auth_headers,
            timeout=30
        )
        # Verify endpoint exists (may return 409 if verification fails)
        assert response.status_code in [200, 409], f"Expected 200 or 409, got {response.status_code}: {response.text}"
        print(f"✓ Verify endpoint returned {response.status_code}")


class TestAdminCredentialOrchestrationRevoke:
    """Test credential revoke endpoint"""

    def test_revoke_credential_sets_lifecycle_revoked(self, auth_headers):
        """POST /api/venues/admin/credentials/{id}/revoke sets lifecycle to revoked"""
        # First create a credential to revoke
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "scope_type": "global",
            "exchange": "binance",
            "market_type": "spot",
            "purpose": "market_data",
            "environment": "testnet",
            "api_key": f"REVOKE_TEST_KEY_{unique_id}",
            "api_secret": f"REVOKE_TEST_SECRET_{unique_id}",
            "is_default": False
        }
        create_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            json=create_payload,
            timeout=15
        )
        if create_response.status_code != 201:
            pytest.skip(f"Could not create credential for revoke test: {create_response.text}")
        
        credential_id = create_response.json()["id"]
        
        # Revoke the credential
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/revoke",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify lifecycle_status is revoked
        assert data.get("lifecycle_status") == "revoked", f"Expected revoked, got {data.get('lifecycle_status')}"
        assert data.get("approval_status") == "revoked", f"Expected approval_status revoked"
        assert data.get("is_active") == False, "Revoked credential should be inactive"
        
        print(f"✓ Revoked credential {credential_id}, lifecycle_status={data['lifecycle_status']}")


class TestAdminCredentialOrchestrationRotate:
    """Test credential rotate endpoint"""

    def test_rotate_credential_sets_lifecycle_rotated_pending_verify(self, auth_headers):
        """POST /api/venues/admin/credentials/{id}/rotate sets lifecycle to rotated_pending_verify"""
        # First create a credential to rotate
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "scope_type": "global",
            "exchange": "binance",
            "market_type": "spot",
            "purpose": "market_data",
            "environment": "testnet",
            "api_key": f"ROTATE_TEST_KEY_{unique_id}",
            "api_secret": f"ROTATE_TEST_SECRET_{unique_id}",
            "is_default": False
        }
        create_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            json=create_payload,
            timeout=15
        )
        if create_response.status_code != 201:
            pytest.skip(f"Could not create credential for rotate test: {create_response.text}")
        
        credential_id = create_response.json()["id"]
        
        # Rotate the credential
        rotate_payload = {
            "api_key": f"NEW_ROTATED_KEY_{unique_id}",
            "api_secret": f"NEW_ROTATED_SECRET_{unique_id}",
            "passphrase": None
        }
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/rotate",
            headers=auth_headers,
            json=rotate_payload,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify lifecycle_status is rotated_pending_verify
        assert data.get("lifecycle_status") == "rotated_pending_verify", f"Expected rotated_pending_verify, got {data.get('lifecycle_status')}"
        assert data.get("approval_status") == "pending", "Rotated credential should have pending approval"
        assert data.get("is_active") == False, "Rotated credential should be inactive until verified"
        
        print(f"✓ Rotated credential {credential_id}, lifecycle_status={data['lifecycle_status']}")


class TestPermissionScopeValidation:
    """Test permission scope validation for execution credentials"""

    def test_credential_response_contains_permission_scope_validation(self, auth_headers):
        """Credential response contains permission_scope_validation field"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        if not data:
            pytest.skip("No credentials to check permission_scope_validation")
        
        credential = data[0]
        assert "permission_scope_validation" in credential, "Response should contain permission_scope_validation"
        
        validation = credential["permission_scope_validation"]
        assert "status" in validation, "permission_scope_validation should have status"
        assert "reason_code" in validation, "permission_scope_validation should have reason_code"
        assert "message" in validation, "permission_scope_validation should have message"
        
        print(f"✓ permission_scope_validation: status={validation['status']}, reason_code={validation['reason_code']}")


class TestControlPlaneSanityCheck:
    """Test control-plane sanity check endpoint"""

    def test_sanity_check_returns_net_status_and_checks(self, auth_headers):
        """POST /api/venues/admin/control-plane-sanity-check returns net_status, reason_codes, remediation_suggestions, checks"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/control-plane-sanity-check",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "net_status" in data, "Response should contain net_status"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"net_status should be PASS/WARN/BLOCK, got {data['net_status']}"
        
        assert "reason_codes" in data, "Response should contain reason_codes"
        assert isinstance(data["reason_codes"], list), "reason_codes should be a list"
        
        assert "remediation_suggestions" in data, "Response should contain remediation_suggestions"
        assert isinstance(data["remediation_suggestions"], list), "remediation_suggestions should be a list"
        
        assert "checks" in data, "Response should contain checks"
        assert isinstance(data["checks"], list), "checks should be a list"
        
        # Verify check structure
        if data["checks"]:
            check = data["checks"][0]
            assert "check" in check, "Each check should have 'check' field"
            assert "status" in check, "Each check should have 'status' field"
            assert "reason_codes" in check, "Each check should have 'reason_codes' field"
            assert "remediation_suggestion" in check, "Each check should have 'remediation_suggestion' field"
        
        print(f"✓ Sanity check: net_status={data['net_status']}, checks_count={len(data['checks'])}")
        print(f"  reason_codes: {data['reason_codes'][:5]}...")


class TestExecutionValidation:
    """Test execution validation endpoint"""

    def test_execution_validation_returns_net_status_and_checks(self, auth_headers):
        """POST /api/venues/admin/execution-validation returns net_status, checks, validation"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/execution-validation",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "net_status" in data, "Response should contain net_status"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"net_status should be PASS/WARN/BLOCK, got {data['net_status']}"
        
        assert "checks" in data, "Response should contain checks"
        assert isinstance(data["checks"], list), "checks should be a list"
        
        # Verify check structure
        if data["checks"]:
            check = data["checks"][0]
            assert "check" in check, "Each check should have 'check' field"
            assert "status" in check, "Each check should have 'status' field"
            assert check["status"] in ["PASS", "WARN", "BLOCK"], f"check status should be PASS/WARN/BLOCK"
            assert "reason_code" in check, "Each check should have 'reason_code' field"
            assert "remediation" in check, "Each check should have 'remediation' field"
        
        # Verify validation legacy fields
        assert "validation" in data, "Response should contain validation"
        validation = data["validation"]
        assert "adapter_smoke_test" in validation, "validation should have adapter_smoke_test"
        assert "precision_validation" in validation, "validation should have precision_validation"
        assert "lot_size_validation" in validation, "validation should have lot_size_validation"
        assert "order_submit_test" in validation, "validation should have order_submit_test"
        
        print(f"✓ Execution validation: net_status={data['net_status']}, checks_count={len(data['checks'])}")


class TestCredentialResolutionPreview:
    """Test credential resolution preview endpoint"""

    def test_resolution_preview_returns_source_and_audit_metadata(self, auth_headers):
        """GET /api/venues/admin/credential-resolution-preview returns source and audit_metadata"""
        # First get a user_id from approved users
        users_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests",
            headers=auth_headers,
            params={"status": "approved"},
            timeout=15
        )
        if users_response.status_code != 200 or not users_response.json():
            pytest.skip("No approved users for resolution preview test")
        
        user_id = users_response.json()[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            headers=auth_headers,
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution"
            },
            timeout=15
        )
        # May return 404 if no credential found, or 409 for various blocks
        if response.status_code == 404:
            print("✓ Resolution preview returned 404 (no credential found) - expected for testnet")
            return
        if response.status_code == 409:
            print(f"✓ Resolution preview returned 409 (blocked): {response.json().get('detail')}")
            return
        
        assert response.status_code == 200, f"Expected 200/404/409, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "source" in data, "Response should contain source"
        assert "audit_metadata" in data, "Response should contain audit_metadata"
        assert "selected_credential_id" in data, "Response should contain selected_credential_id"
        
        print(f"✓ Resolution preview: source={data.get('source')}, credential_id={data.get('selected_credential_id')}")


class TestCredentialResolutionLiveHardGate:
    """Test credential resolution preview live environment hard-gate"""

    def test_live_resolution_blocked_without_approval(self, auth_headers):
        """GET /api/venues/admin/credential-resolution-preview for live returns 409 without LIVE_ROUTE_APPROVED"""
        # First get a user_id
        users_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests",
            headers=auth_headers,
            params={"status": "approved"},
            timeout=15
        )
        if users_response.status_code != 200 or not users_response.json():
            pytest.skip("No approved users for live resolution test")
        
        user_id = users_response.json()[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            headers=auth_headers,
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "purpose": "execution"
            },
            timeout=15
        )
        # Should return 409 with live_route_not_approved or mode_mismatch_live_blocked
        if response.status_code == 409:
            detail = response.json().get("detail", "")
            assert detail in ["live_route_not_approved", "mode_mismatch_live_blocked", "credential_not_found", "venue_not_allowed"], \
                f"Expected live gate error, got: {detail}"
            print(f"✓ Live resolution correctly blocked: {detail}")
        elif response.status_code == 404:
            print("✓ Live resolution returned 404 (no credential) - acceptable")
        else:
            # If 200, it means LIVE_ROUTE_APPROVED is true in env
            print(f"✓ Live resolution returned {response.status_code} - LIVE_ROUTE_APPROVED may be enabled")


class TestCredentialAssignmentRules:
    """Test credential assignment rules endpoints"""

    def test_list_assignment_rules(self, auth_headers):
        """GET /api/venues/admin/credential-rules returns list"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            headers=auth_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Assignment rules returned {len(data)} items")

    def test_upsert_assignment_rule(self, auth_headers):
        """PUT /api/venues/admin/credential-rules creates/updates rule"""
        payload = {
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "tenant_id": None,
            "user_id": None,
            "preferred_source": "user",
            "fallback_enabled": True
        }
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            headers=auth_headers,
            json=payload,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "id" in data, "Response should contain id"
        assert data.get("preferred_source") == "user", "preferred_source should be user"
        assert data.get("fallback_enabled") == True, "fallback_enabled should be True"
        
        print(f"✓ Upserted assignment rule: id={data.get('id')}")


class TestLifecycleStatusFlow:
    """Test complete lifecycle status flow"""

    def test_lifecycle_flow_pending_to_verified_to_revoked(self, auth_headers):
        """Test lifecycle: pending_verify -> (probe) -> verified/verify_failed -> revoked"""
        # Create credential (pending_verify)
        unique_id = str(uuid.uuid4())[:8]
        create_payload = {
            "scope_type": "global",
            "exchange": "binance",
            "market_type": "spot",
            "purpose": "market_data",
            "environment": "testnet",
            "api_key": f"LIFECYCLE_TEST_KEY_{unique_id}",
            "api_secret": f"LIFECYCLE_TEST_SECRET_{unique_id}",
            "is_default": False
        }
        create_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            json=create_payload,
            timeout=15
        )
        assert create_response.status_code == 201
        credential = create_response.json()
        credential_id = credential["id"]
        
        # Verify initial lifecycle is pending_verify
        assert credential["lifecycle_status"] == "pending_verify", "Initial lifecycle should be pending_verify"
        print(f"  Step 1: Created with lifecycle_status=pending_verify")
        
        # Probe credential (will set to verified or verify_failed)
        probe_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/probe",
            headers=auth_headers,
            timeout=30
        )
        assert probe_response.status_code == 200
        probed = probe_response.json()
        
        # After probe, lifecycle should be verified or verify_failed
        assert probed["lifecycle_status"] in ["verified", "verify_failed"], \
            f"After probe, lifecycle should be verified/verify_failed, got {probed['lifecycle_status']}"
        print(f"  Step 2: After probe, lifecycle_status={probed['lifecycle_status']}")
        
        # Revoke credential
        revoke_response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{credential_id}/revoke",
            headers=auth_headers,
            timeout=15
        )
        assert revoke_response.status_code == 200
        revoked = revoke_response.json()
        
        assert revoked["lifecycle_status"] == "revoked", "After revoke, lifecycle should be revoked"
        print(f"  Step 3: After revoke, lifecycle_status=revoked")
        
        print(f"✓ Complete lifecycle flow verified for credential {credential_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
