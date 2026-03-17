"""
Test cases for:
1. POST /api/admin/users/{user_id}/repair-venue-assignment - repair endpoint
2. GET /api/exchange/validate - assignment_required auto-fix behavior with connection profile
"""
import os
import uuid
from pathlib import Path

import pytest
import requests


def _resolve_base_url() -> str:
    direct = os.environ.get("REACT_APP_BACKEND_URL", "").strip().rstrip("/")
    if direct:
        return direct
    env_file = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            if raw_line.startswith("REACT_APP_BACKEND_URL="):
                return raw_line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _resolve_base_url()
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin12345!")


@pytest.fixture(scope="module")
def admin_headers() -> dict:
    """Get admin auth headers for API calls."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def _register_and_approve_user(admin_headers: dict) -> str:
    """Register a new user and approve them, returning user_id."""
    email = f"repair_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    
    # Register
    response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["id"]
    
    # Approve
    approve = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    assert approve.status_code == 200, approve.text
    return user_id


class TestRepairVenueAssignment:
    """Tests for POST /api/admin/users/{user_id}/repair-venue-assignment endpoint."""

    def test_repair_endpoint_returns_200_for_valid_user(self, admin_headers: dict):
        """Repair endpoint should return 200 for a valid approved user."""
        user_id = _register_and_approve_user(admin_headers)
        
        # Call repair endpoint
        response = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/repair-venue-assignment",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        
        # Verify response structure
        data = response.json()
        assert "user_id" in data
        assert data["user_id"] == user_id
        assert "exchange_code" in data
        assert data["exchange_code"] == "binance"
        assert "assignment_changed" in data
        assert "spot_allowed" in data
        assert "futures_allowed" in data
        assert "testnet_allowed" in data
        assert "live_allowed" in data

    def test_repair_endpoint_sets_proper_permissions(self, admin_headers: dict):
        """Repair endpoint should set proper venue permissions."""
        user_id = _register_and_approve_user(admin_headers)
        
        # Call repair endpoint
        response = requests.post(
            f"{BASE_URL}/api/admin/users/{user_id}/repair-venue-assignment",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, response.text
        
        data = response.json()
        # Verify permissions are set correctly
        assert data["spot_allowed"] is True
        assert data["futures_allowed"] is True
        assert data["testnet_allowed"] is True
        # Live should remain false as per default policy
        assert data["live_allowed"] is False

    def test_repair_endpoint_returns_404_for_nonexistent_user(self, admin_headers: dict):
        """Repair endpoint should return 404 for non-existent user."""
        fake_user_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users/{fake_user_id}/repair-venue-assignment",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 404, response.text
        
        data = response.json()
        assert data.get("detail") == "user_not_found"

    def test_repair_endpoint_returns_400_for_admin_user(self, admin_headers: dict):
        """Repair endpoint should return 400 for non-USER role accounts."""
        # Try to repair admin account - should fail
        admin_login = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        admin_data = admin_login.json()
        admin_user_id = admin_data.get("user", {}).get("id")
        
        if admin_user_id:
            response = requests.post(
                f"{BASE_URL}/api/admin/users/{admin_user_id}/repair-venue-assignment",
                headers=admin_headers,
                timeout=20,
            )
            assert response.status_code == 400, response.text
            assert response.json().get("detail") == "only_user_role_supported"

    def test_repair_endpoint_requires_auth(self):
        """Repair endpoint should require authentication."""
        fake_user_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/api/admin/users/{fake_user_id}/repair-venue-assignment",
            timeout=20,
        )
        assert response.status_code == 401, response.text

    def test_bulk_repair_endpoint_returns_summary(self, admin_headers: dict):
        """Bulk repair endpoint should return processed/changed counts."""
        response = requests.post(
            f"{BASE_URL}/api/admin/users/repair-venue-assignments",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "processed_users" in data
        assert "changed_assignments" in data
        assert int(data["processed_users"]) >= 0
        assert int(data["changed_assignments"]) >= 0


class TestExchangeValidateAutofix:
    """Tests for exchange/validate assignment_required auto-fix behavior."""

    def test_validate_endpoint_exists(self, admin_headers: dict):
        """Exchange validate endpoint should exist and be accessible."""
        _ = _register_and_approve_user(admin_headers)
        
        # Get user token to test validate endpoint
        email = f"validate_test_{uuid.uuid4().hex[:8]}@example.com"
        password = "TestPass123!"
        
        # Register and approve
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password},
            timeout=20,
        )
        assert reg_response.status_code == 200, reg_response.text
        new_user_id = reg_response.json()["id"]
        
        # Approve user
        approve = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{new_user_id}/approve",
            headers=admin_headers,
            timeout=20,
        )
        assert approve.status_code == 200, approve.text
        
        # Login as user
        login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=20,
        )
        assert login.status_code == 200, login.text
        user_token = login.json().get("access_token")
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        # Call validate endpoint
        response = requests.get(
            f"{BASE_URL}/api/exchange/validate",
            params={"exchange": "binance", "market_type": "futures", "environment": "testnet"},
            headers=user_headers,
            timeout=20,
        )
        # Endpoint should return something (200 for valid, 400/403 for invalid credentials/permissions)
        assert response.status_code in [200, 400, 403], f"Unexpected status: {response.status_code}, {response.text}"


class TestSingleApproveVenueAssignment:
    """Additional tests for single user approval auto-provisioning."""

    def test_approve_creates_venue_assignment(self, admin_headers: dict):
        """Single approval should create venue assignment automatically."""
        email = f"single_approve_{uuid.uuid4().hex[:8]}@example.com"
        password = "TestPass123!"
        
        # Register
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password},
            timeout=20,
        )
        assert response.status_code == 200, response.text
        user_id = response.json()["id"]
        
        # Approve
        approve = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=admin_headers,
            timeout=20,
        )
        assert approve.status_code == 200, approve.text
        
        # Verify assignment was created
        assignments = requests.get(
            f"{BASE_URL}/api/venues/admin/user-assignments",
            params={"user_id": user_id},
            headers=admin_headers,
            timeout=20,
        )
        assert assignments.status_code == 200, assignments.text
        rows = assignments.json()
        
        # Should have at least one binance assignment
        binance_rows = [row for row in rows if row.get("exchange_code") == "binance"]
        assert len(binance_rows) >= 1
        assert binance_rows[0].get("futures_allowed") is True
        assert binance_rows[0].get("testnet_allowed") is True


class TestBulkApproveVenueAssignment:
    """Additional tests for bulk approval auto-provisioning."""

    def test_bulk_approve_creates_venue_assignments_for_multiple_users(self, admin_headers: dict):
        """Bulk approval should create venue assignments for all approved users."""
        user_ids = []
        for i in range(2):
            email = f"bulk_test_{uuid.uuid4().hex[:8]}@example.com"
            password = "TestPass123!"
            
            response = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": password},
                timeout=20,
            )
            assert response.status_code == 200, response.text
            user_ids.append(response.json()["id"])
        
        # Bulk approve
        bulk = requests.post(
            f"{BASE_URL}/api/admin/user-approvals/bulk-approve",
            headers=admin_headers,
            json={"ids": user_ids},
            timeout=20,
        )
        assert bulk.status_code == 200, bulk.text
        
        bulk_data = bulk.json()
        assert bulk_data.get("count") == 2
        
        # Verify assignments for each user
        for user_id in user_ids:
            assignments = requests.get(
                f"{BASE_URL}/api/venues/admin/user-assignments",
                params={"user_id": user_id},
                headers=admin_headers,
                timeout=20,
            )
            assert assignments.status_code == 200, assignments.text
            rows = assignments.json()
            
            binance_rows = [row for row in rows if row.get("exchange_code") == "binance"]
            assert len(binance_rows) >= 1
