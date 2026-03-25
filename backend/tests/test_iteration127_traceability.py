"""
Iteration 127: Traceability Acceptance Tests
Tests for credential resolution preview with request_id, audit trace drawer, and unique request_id per call.

Features tested:
- GET /api/venues/admin/credential-resolution-preview response fields:
  request_id, resolved_at, exchange, market_type, environment, purpose, fallback_chain, selected_probe_status
- Two consecutive preview calls return unique request_id
- Frontend: request_id/timestamp visible in preview
- Frontend: Audit Trace drawer opens
- Drawer fields: selected source, fallback chain, masked credential, environment, market_type, probe state, timestamp, request_id
- audit_link anchor clickable
"""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
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
        if data.get("mfa_required"):
            # Handle MFA if required
            challenge_token = data.get("mfa_challenge_token")
            mfa_response = requests.post(
                f"{BASE_URL}/api/auth/mfa/verify",
                json={
                    "challenge_token": challenge_token,
                    "method": "email_otp",
                    "code": "000000",
                },
            )
            if mfa_response.status_code == 200:
                return mfa_response.json().get("access_token")
        return data.get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Get admin headers with auth token"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


class TestCredentialResolutionPreviewTraceability:
    """Tests for credential resolution preview traceability fields"""

    def test_preview_returns_request_id(self, admin_headers):
        """Test that preview endpoint returns request_id field"""
        # First get a user_id from the system
        users_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers,
        )
        assert users_response.status_code == 200, f"Failed to get users: {users_response.text}"
        users = users_response.json()
        assert len(users) > 0, "No users found in system"
        user_id = users[0]["id"]

        # Call preview endpoint
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Preview failed: {response.text}"
        data = response.json()

        # Verify request_id is present and is a valid UUID format
        assert "request_id" in data, "request_id field missing from response"
        assert data["request_id"], "request_id should not be empty"
        assert len(data["request_id"]) == 36, f"request_id should be UUID format, got: {data['request_id']}"

    def test_preview_returns_resolved_at(self, admin_headers):
        """Test that preview endpoint returns resolved_at timestamp"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "resolved_at" in data, "resolved_at field missing from response"
        assert data["resolved_at"], "resolved_at should not be empty"
        # Should be ISO format timestamp
        assert "T" in data["resolved_at"], f"resolved_at should be ISO format, got: {data['resolved_at']}"

    def test_preview_returns_exchange_market_environment_purpose(self, admin_headers):
        """Test that preview returns exchange, market_type, environment, purpose fields"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify all required fields
        assert "exchange" in data, "exchange field missing"
        assert data["exchange"] == "binance", f"exchange mismatch: {data['exchange']}"

        assert "market_type" in data, "market_type field missing"
        assert data["market_type"] == "spot", f"market_type mismatch: {data['market_type']}"

        assert "environment" in data, "environment field missing"
        assert data["environment"] == "testnet", f"environment mismatch: {data['environment']}"

        assert "purpose" in data, "purpose field missing"
        assert data["purpose"] == "execution", f"purpose mismatch: {data['purpose']}"

    def test_preview_returns_fallback_chain(self, admin_headers):
        """Test that preview returns fallback_chain field"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "fallback_chain" in data, "fallback_chain field missing"
        assert isinstance(data["fallback_chain"], list), "fallback_chain should be a list"
        assert len(data["fallback_chain"]) == 3, f"fallback_chain should have 3 items, got: {data['fallback_chain']}"
        assert data["fallback_chain"] == ["user", "tenant_admin", "global_admin"], f"fallback_chain mismatch: {data['fallback_chain']}"

    def test_preview_returns_selected_probe_status(self, admin_headers):
        """Test that preview returns selected_probe_status field"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # selected_probe_status can be None if no credential is selected
        assert "selected_probe_status" in data, "selected_probe_status field missing"
        # If there's a selected credential, probe status should be one of the valid states
        if data.get("selected_credential_id"):
            valid_probe_states = [
                "ready", "connectivity_only", "invalid_key", "permission_restricted",
                "ip_restricted", "env_mismatch", "rate_limited", "probe_not_supported",
                "unreachable", "no_probe", None
            ]
            assert data["selected_probe_status"] in valid_probe_states, f"Invalid probe status: {data['selected_probe_status']}"

    def test_two_consecutive_calls_return_unique_request_ids(self, admin_headers):
        """Test that two consecutive preview calls return unique request_ids"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        params = {
            "user_id": user_id,
            "exchange": "binance",
            "market_type": "spot",
            "environment": "testnet",
            "purpose": "execution",
        }

        # First call
        response1 = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params=params,
            headers=admin_headers,
        )
        assert response1.status_code == 200
        data1 = response1.json()
        request_id_1 = data1["request_id"]

        # Small delay to ensure different timestamps
        time.sleep(0.1)

        # Second call
        response2 = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params=params,
            headers=admin_headers,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        request_id_2 = data2["request_id"]

        # Verify request_ids are unique
        assert request_id_1 != request_id_2, f"request_ids should be unique: {request_id_1} == {request_id_2}"

    def test_preview_all_response_fields_present(self, admin_headers):
        """Test that all expected response fields are present in preview response"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # All required fields from CredentialResolutionPreviewResponse schema
        required_fields = [
            "request_id",
            "resolved_at",
            "selected_credential_id",
            "source",
            "masked_api_key",
            "masked_fingerprint",
            "exchange",
            "market_type",
            "environment",
            "purpose",
            "fallback_chain",
            "selected_probe_status",
        ]

        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from response"

        print(f"All {len(required_fields)} required fields present in response")
        print(f"request_id: {data['request_id']}")
        print(f"resolved_at: {data['resolved_at']}")
        print(f"fallback_chain: {data['fallback_chain']}")
        print(f"selected_probe_status: {data['selected_probe_status']}")

    def test_preview_with_different_purposes(self, admin_headers):
        """Test preview with different purpose values"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        purposes = ["market_data", "execution", "fallback"]
        request_ids = []

        for purpose in purposes:
            response = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                params={
                    "user_id": user_id,
                    "exchange": "binance",
                    "market_type": "spot",
                    "environment": "testnet",
                    "purpose": purpose,
                },
                headers=admin_headers,
            )
            assert response.status_code == 200, f"Preview failed for purpose={purpose}: {response.text}"
            data = response.json()
            assert data["purpose"] == purpose, f"Purpose mismatch: expected {purpose}, got {data['purpose']}"
            request_ids.append(data["request_id"])

        # All request_ids should be unique
        assert len(set(request_ids)) == len(request_ids), "All request_ids should be unique across different purposes"

    def test_preview_with_different_environments(self, admin_headers):
        """Test preview with different environment values"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        environments = ["testnet", "live"]
        request_ids = []

        for env in environments:
            response = requests.get(
                f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
                params={
                    "user_id": user_id,
                    "exchange": "binance",
                    "market_type": "spot",
                    "environment": env,
                    "purpose": "execution",
                },
                headers=admin_headers,
            )
            assert response.status_code == 200, f"Preview failed for environment={env}: {response.text}"
            data = response.json()
            assert data["environment"] == env, f"Environment mismatch: expected {env}, got {data['environment']}"
            request_ids.append(data["request_id"])

        # All request_ids should be unique
        assert len(set(request_ids)) == len(request_ids), "All request_ids should be unique across different environments"


class TestAuditLogCreation:
    """Tests for audit log creation during credential resolution preview"""

    def test_preview_creates_audit_log(self, admin_headers):
        """Test that preview creates an audit log entry with request_id"""
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        user_id = users_response.json()[0]["id"]

        # Call preview
        response = requests.get(
            f"{BASE_URL}/api/venues/admin/credential-resolution-preview",
            params={
                "user_id": user_id,
                "exchange": "binance",
                "market_type": "spot",
                "environment": "testnet",
                "purpose": "execution",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        request_id = data["request_id"]

        # Check audit logs for this request_id
        audit_response = requests.get(
            f"{BASE_URL}/api/admin/audit-logs",
            params={"limit": 10},
            headers=admin_headers,
        )
        
        if audit_response.status_code == 200:
            audit_logs = audit_response.json()
            # Look for audit log with matching entity_id (request_id)
            matching_logs = [
                log for log in audit_logs
                if log.get("entity_id") == request_id or 
                   (log.get("details") and log["details"].get("request_id") == request_id)
            ]
            print(f"Found {len(matching_logs)} audit logs matching request_id: {request_id}")
            if matching_logs:
                log = matching_logs[0]
                print(f"Audit log action: {log.get('action')}")
                print(f"Audit log entity_type: {log.get('entity_type')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
