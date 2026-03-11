"""
Test Suite for User Approval Flow (Iteration 9)
Features tested:
- Separate admin/user login endpoints
- User registration -> pending approval status
- Admin approval/reject APIs
- Role mismatch redirection
"""

import os
import random
import string

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@platform.dev"
ADMIN_PASSWORD = "Admin12345!"


def generate_test_email():
    """Generate a unique test email"""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"TEST_user_{suffix}@example.com"


class TestHealthCheck:
    """Basic health check"""

    def test_api_root(self):
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "phase" in data
        print(f"API Root OK: {data}")


class TestAdminLogin:
    """Admin login endpoint tests"""

    def test_admin_login_success(self):
        """Admin can login via /auth/login/admin"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["role"] == "admin"
        print(f"Admin login success: {data['user']['email']}, role={data['user']['role']}")

    def test_admin_login_wrong_credentials(self):
        """Admin login with wrong password fails"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": "wrongpassword"},
        )
        assert response.status_code == 401
        print("Admin login with wrong password correctly rejected")

    def test_user_cannot_use_admin_login(self):
        """A user trying to login via admin endpoint gets 403"""
        # First create and approve a test user
        test_email = generate_test_email()
        test_password = "TestPassword123!"

        # Register user
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": test_password},
        )
        assert reg_response.status_code == 200
        user_id = reg_response.json()["id"]

        # Get admin token
        admin_response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        admin_token = admin_response.json()["access_token"]

        # Approve user
        approve_response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert approve_response.status_code == 200

        # Now try to login user via admin endpoint
        user_admin_login = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": test_email, "password": test_password},
        )
        assert user_admin_login.status_code == 403
        assert "Yanlış giriş paneli" in user_admin_login.json().get("detail", "")
        print(f"User {test_email} correctly blocked from admin login: 403 Yanlış giriş paneli")


class TestUserLoginEndpoint:
    """User login endpoint tests"""

    def test_user_login_endpoint_exists(self):
        """/auth/login/user endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": "nonexistent@test.com", "password": "anything"},
        )
        # Should be 401 (invalid credentials), not 404 (not found)
        assert response.status_code == 401
        print("User login endpoint exists and responds correctly")

    def test_admin_cannot_use_user_login(self):
        """Admin trying to login via user endpoint gets 403"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 403
        assert "Yanlış giriş paneli" in response.json().get("detail", "")
        print("Admin correctly blocked from user login: 403 Yanlış giriş paneli")


class TestUserRegistrationAndApprovalFlow:
    """Full user registration and approval flow"""

    def test_register_creates_pending_user(self):
        """New user registration creates user with pending status"""
        test_email = generate_test_email()
        test_password = "TestPassword123!"

        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": test_password},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["email"] == test_email
        assert data["role"] == "user"
        assert data["approval_status"] == "pending"
        assert data["is_active"] == False
        print(f"User registered: {test_email}, status={data['approval_status']}, active={data['is_active']}")

    def test_pending_user_cannot_login(self):
        """Pending user gets 403 with approval message"""
        test_email = generate_test_email()
        test_password = "TestPassword123!"

        # Register
        requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": test_password},
        )

        # Try to login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": test_email, "password": test_password},
        )
        assert login_response.status_code == 403
        detail = login_response.json().get("detail", "")
        assert "admin onayı bekliyor" in detail.lower() or "onay" in detail.lower()
        print(f"Pending user login blocked: {detail}")

    def test_admin_can_list_pending_requests(self):
        """Admin can list pending user approval requests"""
        # Get admin token
        admin_response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        admin_token = admin_response.json()["access_token"]

        # List pending
        list_response = requests.get(
            f"{BASE_URL}/api/auth/admin/user-approval-requests?status=pending",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert isinstance(data, list)
        print(f"Pending approval requests: {len(data)} users")

    def test_admin_approve_user_flow(self):
        """Full flow: register -> admin approve -> user can login"""
        test_email = generate_test_email()
        test_password = "TestPassword123!"

        # Step 1: Register user
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": test_password},
        )
        assert reg_response.status_code == 200
        user_id = reg_response.json()["id"]
        print(f"Step 1: User registered with id={user_id}")

        # Step 2: Verify user cannot login (pending)
        login_pending = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": test_email, "password": test_password},
        )
        assert login_pending.status_code == 403
        print("Step 2: Pending user correctly blocked from login")

        # Step 3: Admin gets token
        admin_response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        admin_token = admin_response.json()["access_token"]
        print("Step 3: Admin logged in")

        # Step 4: Admin approves user
        approve_response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert approve_response.status_code == 200
        approved_user = approve_response.json()
        assert approved_user["approval_status"] == "approved"
        assert approved_user["is_active"] == True
        print(f"Step 4: User approved, status={approved_user['approval_status']}, active={approved_user['is_active']}")

        # Step 5: User can now login
        login_approved = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": test_email, "password": test_password},
        )
        assert login_approved.status_code == 200
        login_data = login_approved.json()
        assert "access_token" in login_data
        assert login_data["user"]["email"] == test_email
        print(f"Step 5: Approved user logged in successfully: {login_data['user']['email']}")

    def test_admin_reject_user_flow(self):
        """Flow: register -> admin reject -> user cannot login"""
        test_email = generate_test_email()
        test_password = "TestPassword123!"

        # Register user
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": test_email, "password": test_password},
        )
        user_id = reg_response.json()["id"]
        print(f"User registered: {test_email}")

        # Admin rejects
        admin_response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        admin_token = admin_response.json()["access_token"]

        reject_response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert reject_response.status_code == 200
        rejected_user = reject_response.json()
        assert rejected_user["approval_status"] == "rejected"
        assert rejected_user["is_active"] == False
        print(f"User rejected: status={rejected_user['approval_status']}")

        # Rejected user cannot login
        login_rejected = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": test_email, "password": test_password},
        )
        assert login_rejected.status_code == 403
        detail = login_rejected.json().get("detail", "")
        assert "reddedildi" in detail.lower()
        print(f"Rejected user blocked: {detail}")


class TestGenericLoginEndpoint:
    """Test the generic /auth/login endpoint still works"""

    def test_generic_login_admin(self):
        """Generic login works for admin"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["role"] == "admin"
        print("Generic login works for admin")


class TestMeEndpoint:
    """Test /auth/me endpoint"""

    def test_me_returns_user_info(self):
        """Authenticated user can get their info"""
        # Login as admin
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        token = login_response.json()["access_token"]

        # Call /me
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_response.status_code == 200
        data = me_response.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        print(f"/auth/me returns: {data['email']}, role={data['role']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
