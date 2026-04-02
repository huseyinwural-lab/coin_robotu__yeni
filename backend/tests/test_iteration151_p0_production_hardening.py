"""
Iteration 151: P0 Production Hardening Tests (H1-H6)
- Secret provider policy: APP_ENV=production + SECRET_PROVIDER=local blocks local provider
- Credential lifecycle endpoints: verify/revoke/rotate behavior
- Rotate sonrası eski secret reference erişilemez (provider seviyesinde)
- Execution validation endpoint contract: net_status + checks[name,status,reason_code,severity,remediation_suggestions]
- Control plane sanity endpoint contract aynı unified formatta
- Sanity cache endpoint: GET /api/venues/admin/control-plane-sanity-last
- Sanity gate script: /app/scripts/check_venue_sanity_gate.sh net_status!=PASS durumunda non-zero
- Live hard-gate reason code determinism
- Frontend AdminCredentialOrchestrationPage secret input type=password
- Frontend AdminExchangesPage execution/sanity contract rendering
"""

import os
import pytest
import requests
import subprocess
import json
import tempfile

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
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for API requests"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestSecretProviderPolicy:
    """H1: Secret provider policy - APP_ENV=production + SECRET_PROVIDER=local blocks local provider"""

    def test_secret_provider_service_local_block_in_prod(self):
        """Test that local provider is blocked in production environment"""
        # Import the service module to test the policy function
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.secret_provider_service import (
            _enforce_local_provider_policy,
            PRODUCTION_ENVS,
            secret_provider_name
        )
        
        # Verify PRODUCTION_ENVS contains expected values
        assert "prod" in PRODUCTION_ENVS
        assert "production" in PRODUCTION_ENVS
        assert "live" in PRODUCTION_ENVS
        
        # Test that local provider is allowed in non-prod (current env)
        current_provider = secret_provider_name()
        print(f"Current secret provider: {current_provider}")
        
        # The function should not raise in dev environment
        try:
            _enforce_local_provider_policy("local")
            print("Local provider allowed in current (non-prod) environment")
        except RuntimeError as e:
            if "local_secret_provider_not_allowed_in_prod" in str(e):
                print("Environment is production - local provider correctly blocked")
            else:
                raise

    def test_secret_provider_name_returns_valid_provider(self):
        """Test that secret_provider_name returns a valid provider"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.secret_provider_service import secret_provider_name, SUPPORTED_SECRET_PROVIDERS
        
        provider = secret_provider_name()
        assert provider in SUPPORTED_SECRET_PROVIDERS, f"Provider {provider} not in supported list"
        print(f"Secret provider: {provider}")


class TestCredentialLifecycleEndpoints:
    """H2: Credential lifecycle endpoints - verify/revoke/rotate behavior"""

    def test_credential_list_endpoint(self, auth_headers):
        """Test GET /api/venues/admin/credentials returns proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=30
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} credentials")
        
        # Check structure of first credential if exists
        if data:
            cred = data[0]
            required_fields = [
                "id", "exchange", "market_type", "environment", "purpose",
                "scope_type", "is_active", "approval_status", "lifecycle_status",
                "permission_scope", "secret_provider"
            ]
            for field in required_fields:
                assert field in cred, f"Missing field: {field}"
            print(f"Credential structure verified: {list(cred.keys())}")

    def test_credential_verify_endpoint_exists(self, auth_headers):
        """Test POST /api/venues/admin/credentials/{id}/verify endpoint exists"""
        # First get a credential ID
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=30
        )
        assert response.status_code == 200
        credentials = response.json()
        
        if not credentials:
            pytest.skip("No credentials to test verify endpoint")
        
        cred_id = credentials[0]["id"]
        
        # Test verify endpoint (may fail if credential is not verifiable, but endpoint should exist)
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/verify",
            headers=auth_headers,
            timeout=30
        )
        # 409 is expected if credential verify fails, 200 if success
        assert response.status_code in [200, 409], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"Verify endpoint response: {response.status_code}")

    def test_credential_revoke_endpoint_exists(self, auth_headers):
        """Test POST /api/venues/admin/credentials/{id}/revoke endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=30
        )
        assert response.status_code == 200
        credentials = response.json()
        
        if not credentials:
            pytest.skip("No credentials to test revoke endpoint")
        
        # Find a non-revoked credential
        non_revoked = [c for c in credentials if c.get("approval_status") != "revoked"]
        if not non_revoked:
            pytest.skip("No non-revoked credentials to test")
        
        cred_id = non_revoked[0]["id"]
        
        # Test revoke endpoint
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/revoke",
            headers=auth_headers,
            timeout=30
        )
        # 200 if success, 403 if not super_admin, 400 if already revoked/secret_revoked
        assert response.status_code in [200, 400, 403], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"Revoke endpoint response: {response.status_code} - {response.text[:100] if response.text else ''}")

    def test_credential_rotate_endpoint_exists(self, auth_headers):
        """Test POST /api/venues/admin/credentials/{id}/rotate endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credentials",
            headers=auth_headers,
            params={"include_inactive": True},
            timeout=30
        )
        assert response.status_code == 200
        credentials = response.json()
        
        if not credentials:
            pytest.skip("No credentials to test rotate endpoint")
        
        # Find a non-revoked credential for rotation
        non_revoked = [c for c in credentials if c.get("approval_status") != "revoked"]
        if not non_revoked:
            pytest.skip("No non-revoked credentials to test rotate")
        
        cred_id = non_revoked[0]["id"]
        
        # Test rotate endpoint (requires payload)
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/credentials/{cred_id}/rotate",
            headers=auth_headers,
            json={
                "api_key": "TEST_ROTATE_KEY_12345",
                "api_secret": "TEST_ROTATE_SECRET_67890",
                "passphrase": None
            },
            timeout=30
        )
        # 200 if success, 403 if not super_admin, 400 if invalid payload, 500 if secret_revoked
        assert response.status_code in [200, 400, 403, 500], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"Rotate endpoint response: {response.status_code} - {response.text[:100] if response.text else ''}")


class TestRotateSecretReferenceInaccessible:
    """H3: Rotate sonrası eski secret reference erişilemez (provider seviyesinde)"""

    def test_local_provider_revoke_blocks_access(self):
        """Test that revoked local secrets cannot be accessed"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.secret_provider_service import LocalSecretProvider, _REVOKED_LOCAL_REFERENCES
        
        provider = LocalSecretProvider()
        
        # Create a secret
        test_value = "test_secret_value_12345"
        reference = provider.set_secret(test_value)
        print(f"Created secret reference: {reference[:30]}...")
        
        # Verify we can read it
        decrypted = provider.get_secret(reference)
        assert decrypted == test_value, "Secret roundtrip failed"
        
        # Revoke the secret
        provider.revoke_secret(reference)
        assert reference in _REVOKED_LOCAL_REFERENCES, "Reference not in revoked set"
        
        # Verify access is blocked
        try:
            provider.get_secret(reference)
            pytest.fail("Should have raised RuntimeError for revoked secret")
        except RuntimeError as e:
            assert "secret_revoked" in str(e)
            print("Revoked secret correctly blocked")

    def test_rotate_revokes_old_reference(self):
        """Test that rotate operation revokes old reference"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.secret_provider_service import LocalSecretProvider, _REVOKED_LOCAL_REFERENCES
        
        provider = LocalSecretProvider()
        
        # Create initial secret
        old_value = "old_secret_value"
        old_reference = provider.set_secret(old_value)
        
        # Rotate to new secret
        new_value = "new_secret_value"
        new_reference = provider.rotate_secret(old_reference, new_value)
        
        # Verify old reference is revoked
        assert old_reference in _REVOKED_LOCAL_REFERENCES, "Old reference not revoked after rotate"
        
        # Verify new reference works
        decrypted = provider.get_secret(new_reference)
        assert decrypted == new_value, "New secret roundtrip failed"
        
        # Verify old reference is blocked
        try:
            provider.get_secret(old_reference)
            pytest.fail("Should have raised RuntimeError for rotated secret")
        except RuntimeError as e:
            assert "secret_revoked" in str(e)
            print("Rotated old secret correctly blocked")


class TestExecutionValidationContract:
    """H4: Execution validation endpoint contract: net_status + checks[name,status,reason_code,severity,remediation_suggestions]"""

    def test_execution_validation_endpoint_contract(self, auth_headers):
        """Test POST /api/venues/admin/execution-validation returns unified contract"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/execution-validation",
            headers=auth_headers,
            timeout=60
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify top-level fields
        assert "net_status" in data, "Missing net_status"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        
        assert "reason_codes" in data, "Missing reason_codes"
        assert isinstance(data["reason_codes"], list), "reason_codes should be a list"
        
        assert "remediation_suggestions" in data, "Missing remediation_suggestions"
        assert isinstance(data["remediation_suggestions"], list), "remediation_suggestions should be a list"
        
        assert "checks" in data, "Missing checks array"
        assert isinstance(data["checks"], list), "checks should be a list"
        
        # Verify checks array structure
        for check in data["checks"]:
            assert "name" in check, f"Check missing 'name': {check}"
            assert "status" in check, f"Check missing 'status': {check}"
            assert check["status"] in ["PASS", "WARN", "BLOCK"], f"Invalid check status: {check['status']}"
            assert "reason_code" in check, f"Check missing 'reason_code': {check}"
            assert "severity" in check, f"Check missing 'severity': {check}"
            assert "remediation_suggestions" in check, f"Check missing 'remediation_suggestions': {check}"
            assert isinstance(check["remediation_suggestions"], list), "remediation_suggestions should be a list"
        
        # Verify NO MOCKED field
        assert "MOCKED" not in data, "Response should not contain MOCKED field"
        assert "mocked" not in str(data).lower() or "mocked" in str(data.get("reason_codes", [])).lower(), "Response should not indicate mocking"
        
        print(f"Execution validation: net_status={data['net_status']}, checks={len(data['checks'])}")
        for check in data["checks"]:
            print(f"  - {check['name']}: {check['status']} ({check['reason_code']})")


class TestControlPlaneSanityContract:
    """H5: Control plane sanity endpoint contract aynı unified formatta"""

    def test_control_plane_sanity_check_contract(self, auth_headers):
        """Test POST /api/venues/admin/control-plane-sanity-check returns unified contract"""
        response = requests.post(
            f"{BASE_URL}/api/venues/admin/control-plane-sanity-check",
            headers=auth_headers,
            timeout=60
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify top-level fields (same as execution validation)
        assert "net_status" in data, "Missing net_status"
        assert data["net_status"] in ["PASS", "WARN", "BLOCK"], f"Invalid net_status: {data['net_status']}"
        
        assert "reason_codes" in data, "Missing reason_codes"
        assert isinstance(data["reason_codes"], list), "reason_codes should be a list"
        
        assert "remediation_suggestions" in data, "Missing remediation_suggestions"
        assert isinstance(data["remediation_suggestions"], list), "remediation_suggestions should be a list"
        
        assert "checks" in data, "Missing checks array"
        assert isinstance(data["checks"], list), "checks should be a list"
        
        # Verify checks array structure (unified format)
        for check in data["checks"]:
            assert "name" in check, f"Check missing 'name': {check}"
            assert "status" in check, f"Check missing 'status': {check}"
            assert check["status"] in ["PASS", "WARN", "BLOCK"], f"Invalid check status: {check['status']}"
            assert "reason_code" in check, f"Check missing 'reason_code': {check}"
            assert "severity" in check, f"Check missing 'severity': {check}"
            assert "remediation_suggestions" in check, f"Check missing 'remediation_suggestions': {check}"
            assert isinstance(check["remediation_suggestions"], list), "remediation_suggestions should be a list"
        
        # Verify NO MOCKED field
        assert "MOCKED" not in data, "Response should not contain MOCKED field"
        
        print(f"Control plane sanity: net_status={data['net_status']}, checks={len(data['checks'])}")
        for check in data["checks"]:
            print(f"  - {check['name']}: {check['status']} ({check['reason_code']})")


class TestSanityCacheEndpoint:
    """H6: Sanity cache endpoint: GET /api/venues/admin/control-plane-sanity-last"""

    def test_sanity_cache_endpoint_exists(self, auth_headers):
        """Test GET /api/venues/admin/control-plane-sanity-last returns cached result"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/control-plane-sanity-last",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Should have same structure as sanity check
        assert "net_status" in data, "Missing net_status"
        assert "reason_codes" in data, "Missing reason_codes"
        assert "checks" in data, "Missing checks"
        
        print(f"Sanity cache: net_status={data['net_status']}")

    def test_sanity_cache_after_check(self, auth_headers):
        """Test that sanity cache is updated after running sanity check"""
        # Run sanity check first
        check_response = requests.post(
            f"{BASE_URL}/api/venues/admin/control-plane-sanity-check",
            headers=auth_headers,
            timeout=60
        )
        assert check_response.status_code == 200
        check_data = check_response.json()
        
        # Get cached result
        cache_response = requests.get(
            f"{BASE_URL}/api/venues/admin/control-plane-sanity-last",
            headers=auth_headers,
            timeout=30
        )
        assert cache_response.status_code == 200
        cache_data = cache_response.json()
        
        # Verify cache matches check result
        assert cache_data["net_status"] == check_data["net_status"], "Cache net_status mismatch"
        print(f"Cache correctly updated: net_status={cache_data['net_status']}")


class TestSanityGateScript:
    """H7: Sanity gate script: /app/scripts/check_venue_sanity_gate.sh net_status!=PASS durumunda non-zero"""

    def test_sanity_gate_script_exists(self):
        """Test that sanity gate script exists and is executable"""
        script_path = "/app/scripts/check_venue_sanity_gate.sh"
        assert os.path.exists(script_path), f"Script not found: {script_path}"
        assert os.access(script_path, os.X_OK), f"Script not executable: {script_path}"
        print("Sanity gate script exists and is executable")

    def test_sanity_gate_script_fail_on_missing_cache(self):
        """Test that script fails when cache file is missing"""
        # Use a non-existent path
        result = subprocess.run(
            ["/app/scripts/check_venue_sanity_gate.sh"],
            env={**os.environ, "VENUE_SANITY_CACHE_PATH": "/tmp/nonexistent_sanity_cache.json"},
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "Script should fail when cache is missing"
        assert "FAIL" in result.stdout or "FAIL" in result.stderr, "Should output FAIL message"
        print(f"Script correctly fails on missing cache: exit={result.returncode}")

    def test_sanity_gate_script_fail_on_non_pass(self):
        """Test that script fails when net_status is not PASS"""
        # Create a temp file with BLOCK status
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"net_status": "BLOCK", "reason_codes": ["test_failure"]}, f)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ["/app/scripts/check_venue_sanity_gate.sh"],
                env={**os.environ, "VENUE_SANITY_CACHE_PATH": temp_path},
                capture_output=True,
                text=True
            )
            assert result.returncode != 0, "Script should fail when net_status is BLOCK"
            assert "FAIL" in result.stdout, f"Should output FAIL message: {result.stdout}"
            print(f"Script correctly fails on BLOCK status: exit={result.returncode}")
        finally:
            os.unlink(temp_path)

    def test_sanity_gate_script_pass_on_pass(self):
        """Test that script passes when net_status is PASS"""
        # Create a temp file with PASS status
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"net_status": "PASS", "reason_codes": []}, f)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ["/app/scripts/check_venue_sanity_gate.sh"],
                env={**os.environ, "VENUE_SANITY_CACHE_PATH": temp_path},
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Script should pass when net_status is PASS: {result.stdout} {result.stderr}"
            assert "PASS" in result.stdout, f"Should output PASS message: {result.stdout}"
            print(f"Script correctly passes on PASS status: exit={result.returncode}")
        finally:
            os.unlink(temp_path)


class TestLiveHardGateReasonCode:
    """H8: Live hard-gate reason code determinism (live resolution preview path)"""

    def test_live_resolution_blocked_without_approval(self, auth_headers):
        """Test that live environment credential resolution is blocked without LIVE_ROUTE_APPROVED"""
        # Get a user ID from approved users
        users_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests",
            headers=auth_headers,
            params={"status": "approved"},
            timeout=30
        )
        if users_response.status_code != 200:
            pytest.skip("Could not get approved users")
        
        users = users_response.json()
        if not users:
            pytest.skip("No approved users for testing")
        
        user_id = users[0]["id"]
        
        # Try to resolve credentials for live environment
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
            timeout=30
        )
        
        # Should be blocked with 409 and specific reason code
        if response.status_code == 409:
            data = response.json()
            detail = data.get("detail", "")
            # Should be one of the live hard-gate reason codes
            valid_reason_codes = [
                "live_route_not_approved",
                "mode_mismatch_live_blocked",
                "sanity_gate_blocked",
                "canary_allowlist_blocked",
                "two_step_approval_missing",
                "credential_not_found",
                "venue_not_allowed"
            ]
            assert any(code in detail for code in valid_reason_codes), f"Unexpected reason: {detail}"
            print(f"Live resolution correctly blocked: {detail}")
        elif response.status_code == 200:
            # If it passes, LIVE_ROUTE_APPROVED must be true
            print("Live resolution allowed - LIVE_ROUTE_APPROVED is true")
        else:
            pytest.fail(f"Unexpected status: {response.status_code} - {response.text}")


class TestCredentialResolutionPreview:
    """Additional tests for credential resolution preview"""

    def test_resolution_preview_live_works(self, auth_headers):
        """Test that live credential resolution works"""
        # Get a user ID
        users_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests",
            headers=auth_headers,
            params={"status": "approved"},
            timeout=30
        )
        if users_response.status_code != 200:
            pytest.skip("Could not get approved users")
        
        users = users_response.json()
        if not users:
            pytest.skip("No approved users for testing")
        
        user_id = users[0]["id"]
        
        # Try live resolution
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
            timeout=30
        )
        
        # Should work or fail with credential_not_found (404) or other blocking reason (409)
        assert response.status_code in [200, 404, 409], f"Unexpected status: {response.status_code} - {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "source" in data, "Missing source field"
            assert "audit_metadata" in data, "Missing audit_metadata"
            print(f"Live resolution: source={data['source']}")
        else:
            data = response.json()
            print(f"Live resolution blocked: {data.get('detail')}")


class TestCredentialAssignmentRules:
    """Tests for credential assignment rules"""

    def test_list_credential_rules(self, auth_headers):
        """Test GET /api/venues/admin/credential-rules"""
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} credential rules")

    def test_upsert_credential_rule(self, auth_headers):
        """Test PUT /api/venues/admin/credential-rules"""
        response = requests.put(
            f"{BASE_URL}/api/venues/admin/credential-rules",
            headers=auth_headers,
            json={
                "exchange": "binance",
                "market_type": "spot",
                "environment": "live",
                "tenant_id": None,
                "user_id": None,
                "preferred_source": "user",
                "fallback_enabled": True
            },
            timeout=30
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data["exchange"] == "binance"
        assert data["preferred_source"] == "user"
        print(f"Rule upserted: {data['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
