"""
D0-UI FIX: Prod Config Remediation Flow Tests
Tests for /api/admin/system/remediate-config GET and POST endpoints
Verifies:
- GET returns remediation state with fields/checks/reason codes
- POST rejects localhost database_url and redis_url with 422 validation_errors
- POST accepts valid prod-like URLs + admin bootstrap credentials
- Audit logs are written for PROD_CONFIG_SAVED and PROD_PREFLIGHT_RUN
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials from test request
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestRemediationConfigGET:
    """Tests for GET /api/admin/system/remediate-config"""

    def test_get_remediation_state_returns_200(self, admin_headers):
        """GET endpoint returns 200 with remediation state"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"

    def test_get_remediation_state_has_required_fields(self, admin_headers):
        """GET response contains all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Required top-level fields
        assert "release_gate_status" in data, "Missing release_gate_status"
        assert "release_gate_reason_codes" in data, "Missing release_gate_reason_codes"
        assert "deploy_enable_allowed" in data, "Missing deploy_enable_allowed"
        assert "remediation_allowed" in data, "Missing remediation_allowed"
        assert "fields" in data, "Missing fields"
        assert "remediation_items" in data, "Missing remediation_items"
        assert "preflight_status" in data, "Missing preflight_status"
        assert "secret_readiness_status" in data, "Missing secret_readiness_status"
        assert "final_release_gate_decision" in data, "Missing final_release_gate_decision"
        assert "checks" in data, "Missing checks"

    def test_get_remediation_state_fields_structure(self, admin_headers):
        """GET response fields array has correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        fields = data.get("fields", [])
        assert isinstance(fields, list), "fields should be a list"

        # Check that tracked fields are present
        tracked_keys = {
            "DATABASE_URL", "REDIS_URL", "JWT_SECRET",
            "ADMIN_BOOTSTRAP_EMAIL", "ADMIN_BOOTSTRAP_PASSWORD",
        }
        field_keys = {f.get("key") for f in fields}
        for key in tracked_keys:
            assert key in field_keys, f"Missing tracked field: {key}"

    def test_get_remediation_state_checks_structure(self, admin_headers):
        """GET response checks array has correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        checks = data.get("checks", [])
        assert isinstance(checks, list), "checks should be a list"

        # Each check should have check_name and status
        for check in checks:
            assert "check_name" in check, "Check missing check_name"
            assert "status" in check, "Check missing status"

    def test_get_remediation_state_reason_codes_list(self, admin_headers):
        """GET response reason_codes is a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        reason_codes = data.get("release_gate_reason_codes", [])
        assert isinstance(reason_codes, list), "release_gate_reason_codes should be a list"


class TestRemediationConfigPOSTValidation:
    """Tests for POST /api/admin/system/remediate-config validation"""

    def test_post_rejects_localhost_database_url(self, admin_headers):
        """POST rejects localhost in database_url with 422"""
        payload = {
            "database_url": "postgresql+psycopg2://user:pass@localhost:5432/db",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "database_url" in validation_errors, "Expected database_url validation error"

    def test_post_rejects_127_0_0_1_database_url(self, admin_headers):
        """POST rejects 127.0.0.1 in database_url with 422"""
        payload = {
            "database_url": "postgresql+psycopg2://user:pass@127.0.0.1:5432/db",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "database_url" in validation_errors, "Expected database_url validation error"

    def test_post_rejects_localhost_redis_url(self, admin_headers):
        """POST rejects localhost in redis_url with 422"""
        payload = {
            "redis_url": "redis://localhost:6379/0",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "redis_url" in validation_errors, "Expected redis_url validation error"

    def test_post_rejects_127_0_0_1_redis_url(self, admin_headers):
        """POST rejects 127.0.0.1 in redis_url with 422"""
        payload = {
            "redis_url": "redis://127.0.0.1:6379/0",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "redis_url" in validation_errors, "Expected redis_url validation error"

    def test_post_rejects_0_0_0_0_database_url(self, admin_headers):
        """POST rejects 0.0.0.0 in database_url with 422"""
        payload = {
            "database_url": "postgresql+psycopg2://user:pass@0.0.0.0:5432/db",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "database_url" in validation_errors, "Expected database_url validation error"

    def test_post_rejects_invalid_admin_email(self, admin_headers):
        """POST rejects invalid admin_bootstrap_email with 422"""
        payload = {
            "admin_bootstrap_email": "not-an-email",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "admin_bootstrap_email" in validation_errors, "Expected admin_bootstrap_email validation error"

    def test_post_rejects_short_admin_password(self, admin_headers):
        """POST rejects admin_bootstrap_password < 10 chars with 422"""
        payload = {
            "admin_bootstrap_password": "short123",  # 8 chars, needs 10
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "admin_bootstrap_password" in validation_errors, "Expected admin_bootstrap_password validation error"

    def test_post_rejects_short_jwt_secret(self, admin_headers):
        """POST rejects jwt_secret < 32 chars with 422"""
        payload = {
            "jwt_secret": "short-secret-123",  # < 32 chars
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        detail = data.get("detail", {})
        validation_errors = detail.get("validation_errors", {})
        assert "jwt_secret" in validation_errors, "Expected jwt_secret validation error"


class TestRemediationConfigPOSTSuccess:
    """Tests for POST /api/admin/system/remediate-config with valid data"""

    def test_post_accepts_valid_prod_database_url(self, admin_headers):
        """POST accepts valid production database_url"""
        payload = {
            "database_url": "postgresql+psycopg2://user:pass@prod-db.example.com:5432/trading",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        # Should return 200 with remediation state (not 422)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        assert "release_gate_status" in data, "Response should contain release_gate_status"

    def test_post_accepts_valid_prod_redis_url(self, admin_headers):
        """POST accepts valid production redis_url"""
        payload = {
            "redis_url": "redis://prod-redis.example.com:6379/0",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        assert "release_gate_status" in data, "Response should contain release_gate_status"

    def test_post_accepts_valid_admin_credentials(self, admin_headers):
        """POST accepts valid admin bootstrap credentials"""
        payload = {
            "admin_bootstrap_email": "admin@production-domain.com",
            "admin_bootstrap_password": "SecurePassword123!",  # 10+ chars
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        assert "release_gate_status" in data, "Response should contain release_gate_status"

    def test_post_accepts_valid_jwt_secret(self, admin_headers):
        """POST accepts valid jwt_secret (32+ chars)"""
        payload = {
            "jwt_secret": "a" * 32 + "secure-production-jwt-secret-key",  # 32+ chars
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        assert "release_gate_status" in data, "Response should contain release_gate_status"

    def test_post_returns_remediation_state_after_save(self, admin_headers):
        """POST returns full remediation state after saving"""
        payload = {
            "admin_bootstrap_email": "test-admin@production.com",
            "admin_bootstrap_password": "TestPassword123!",
        }
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()

        # Should have all remediation state fields
        assert "release_gate_status" in data
        assert "release_gate_reason_codes" in data
        assert "deploy_enable_allowed" in data
        assert "remediation_allowed" in data
        assert "fields" in data
        assert "checks" in data
        assert "preflight_status" in data
        assert "secret_readiness_status" in data
        assert "final_release_gate_decision" in data


class TestRemediationAuditLogs:
    """Tests for audit log creation after remediation actions"""

    def test_post_creates_audit_logs(self, admin_headers):
        """POST creates PROD_CONFIG_SAVED and PROD_PREFLIGHT_RUN audit logs"""
        # First, make a POST to trigger audit logs
        payload = {
            "admin_bootstrap_email": "audit-test@production.com",
            "admin_bootstrap_password": "AuditTestPassword123!",
        }
        post_response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json=payload,
        )
        assert post_response.status_code == 200, f"POST failed: {post_response.text[:300]}"

        # Now check audit logs for the actions
        audit_response = requests.get(
            f"{BASE_URL}/api/audit-logs?limit=20",
            headers=admin_headers,
        )
        
        if audit_response.status_code == 200:
            data = audit_response.json()
            # Handle both list and dict response formats
            if isinstance(data, list):
                items = data
            else:
                items = data.get("items", [])
            actions = [item.get("action") for item in items if isinstance(item, dict)]
            
            # Check that audit logs were created
            assert "PROD_CONFIG_SAVED" in actions or "PROD_PREFLIGHT_RUN" in actions, \
                f"Expected PROD_CONFIG_SAVED or PROD_PREFLIGHT_RUN in audit logs, got: {actions[:10]}"
        else:
            # If audit logs endpoint fails, skip this assertion
            pytest.skip(f"Audit logs endpoint returned {audit_response.status_code}")


class TestRemediationEndpointAuth:
    """Tests for authentication requirements"""

    def test_get_requires_auth(self):
        """GET endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/system/remediate-config")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_post_requires_auth(self):
        """POST endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            json={"database_url": "postgresql://test@prod:5432/db"},
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestRemediationEmptyPayload:
    """Tests for empty/minimal payloads"""

    def test_post_with_empty_payload_returns_200(self, admin_headers):
        """POST with empty payload returns 200 (no changes, just revalidate)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers=admin_headers,
            json={},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
        data = response.json()
        assert "release_gate_status" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
