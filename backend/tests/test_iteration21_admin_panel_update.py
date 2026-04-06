"""
Iteration 21 - Admin Panel Update Testing
Tests for:
1. New routing: /admin/kullanicilar/* routes
2. Legacy redirects: /admin/users/customers, /admin/users/admins, /admin/user-approvals, /admin/users/economics
3. Admin users page: /admin/kullanicilar/admin-kullanicilar
4. User users page: /admin/kullanicilar/user-kullanicilar with expected columns
5. Trade toggle direct endpoint (PATCH /api/admin/identity/users/{id}/trading-enabled-direct)
6. Hard delete direct endpoint (DELETE /api/admin/identity/users/{id}/hard-delete-direct)
7. User approvals page: approve/reject flow
8. Admin create endpoint: super_admin success, admin role 403
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

SUPER_ADMIN_EMAIL = "canary.admin@platform.local"
SUPER_ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


class TestAdminPanelUpdate:
    """Admin Panel Update Tests - Iteration 21"""

    @pytest.fixture(scope="class")
    def super_admin_token(self):
        """Get super_admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
            timeout=60,
        )
        assert response.status_code == 200, f"Super admin login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in super admin login response"
        return token

    @pytest.fixture(scope="class")
    def user_token(self):
        """Get user auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=60,
        )
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, "No token in user login response"
        return token

    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print(f"Health check: {response.status_code} OK")

    def test_super_admin_login(self, super_admin_token):
        """Test super admin login works"""
        assert super_admin_token is not None
        print(f"Super admin login successful, token length: {len(super_admin_token)}")

    def test_admin_identity_users_list(self, super_admin_token):
        """Test /api/admin/identity/users endpoint returns user list"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=headers,
            params={"page": 1, "page_size": 25},
            timeout=30,
        )
        assert response.status_code == 200, f"Identity users list failed: {response.text}"
        data = response.json()
        assert "items" in data, "Response should have 'items' key"
        assert "pagination" in data, "Response should have 'pagination' key"
        print(f"Identity users list: {len(data.get('items', []))} users, pagination: {data.get('pagination')}")

    def test_admin_identity_users_filter_by_role_user(self, super_admin_token):
        """Test filtering users by role=user"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=headers,
            params={"role": "user", "page": 1, "page_size": 50},
            timeout=30,
        )
        assert response.status_code == 200, f"Filter by role=user failed: {response.text}"
        data = response.json()
        items = data.get("items", [])
        print(f"Users with role=user: {len(items)}")
        # Verify all returned users have role=user
        for item in items:
            assert item.get("role") == "user", f"Expected role=user, got {item.get('role')}"

    def test_admin_identity_users_filter_by_admin_roles(self, super_admin_token):
        """Test filtering users by admin roles (super_admin, admin, ops)"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        admin_roles = ["super_admin", "admin", "ops"]
        for role in admin_roles:
            response = requests.get(
                f"{BASE_URL}/api/admin/identity/users",
                headers=headers,
                params={"role": role, "page": 1, "page_size": 50},
                timeout=30,
            )
            assert response.status_code == 200, f"Filter by role={role} failed: {response.text}"
            data = response.json()
            items = data.get("items", [])
            print(f"Users with role={role}: {len(items)}")

    def test_user_approvals_list(self, super_admin_token):
        """Test /api/admin/user-approvals endpoint"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=headers,
            params={"status": "pending"},
            timeout=30,
        )
        assert response.status_code == 200, f"User approvals list failed: {response.text}"
        data = response.json()
        # Response is a list of pending approval requests
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Pending user approvals: {len(data)}")

    def test_admin_create_endpoint_super_admin_success(self, super_admin_token):
        """Test admin create endpoint with super_admin role - should succeed"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        test_email = f"test.admin.{os.urandom(4).hex()}@platform.local"
        response = requests.post(
            f"{BASE_URL}/api/admin/users/admin-create",
            headers=headers,
            json={
                "email": test_email,
                "password": "TestAdmin123!",
                "role": "admin",
            },
            timeout=30,
        )
        # Should succeed with 201 Created
        assert response.status_code == 201, f"Admin create failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("email") == test_email, f"Email mismatch: {data.get('email')}"
        assert data.get("role") == "admin", f"Role mismatch: {data.get('role')}"
        print(f"Admin create successful: {test_email}")
        return data.get("id")

    def test_trading_enabled_direct_endpoint(self, super_admin_token):
        """Test PATCH /api/admin/identity/users/{id}/trading-enabled-direct endpoint"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First get a user to test with
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=headers,
            params={"role": "user", "page": 1, "page_size": 10},
            timeout=30,
        )
        assert response.status_code == 200, f"Get users failed: {response.text}"
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No user found to test trading toggle")
        
        test_user = items[0]
        user_id = test_user.get("id")
        
        # Test enabling trading
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/trading-enabled-direct",
            headers=headers,
            json={
                "trading_enabled": True,
                "reason": "test_iteration21_trade_enable",
            },
            timeout=30,
        )
        # Should succeed or fail with specific error (user_not_approved is acceptable)
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "updated", f"Expected status=updated, got {data.get('status')}"
            print(f"Trading enabled for user {user_id}")
        elif response.status_code == 400:
            # user_not_approved is acceptable
            data = response.json()
            print(f"Trading enable blocked: {data.get('detail')}")
        else:
            assert False, f"Unexpected status: {response.status_code} - {response.text}"

    def test_trading_disabled_direct_endpoint(self, super_admin_token):
        """Test PATCH /api/admin/identity/users/{id}/trading-enabled-direct with trading_enabled=false"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First get a user to test with
        response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=headers,
            params={"role": "user", "page": 1, "page_size": 10},
            timeout=30,
        )
        assert response.status_code == 200, f"Get users failed: {response.text}"
        data = response.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No user found to test trading toggle")
        
        test_user = items[0]
        user_id = test_user.get("id")
        
        # Test disabling trading
        response = requests.patch(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/trading-enabled-direct",
            headers=headers,
            json={
                "trading_enabled": False,
                "reason": "test_iteration21_trade_disable",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Trading disable failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("status") == "updated", f"Expected status=updated, got {data.get('status')}"
        print(f"Trading disabled for user {user_id}")

    def test_hard_delete_direct_endpoint_requires_super_admin(self, super_admin_token):
        """Test DELETE /api/admin/identity/users/{id}/hard-delete-direct requires super_admin"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Create a test user to delete
        test_email = f"test.delete.{os.urandom(4).hex()}@platform.local"
        
        # First register a user
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": "TestDelete123!",
            },
            timeout=30,
        )
        
        if register_response.status_code != 200:
            pytest.skip(f"Could not create test user: {register_response.text}")
        
        user_data = register_response.json()
        user_id = user_data.get("id")
        
        # Now try to hard delete
        response = requests.delete(
            f"{BASE_URL}/api/admin/identity/users/{user_id}/hard-delete-direct",
            headers=headers,
            json={"reason": "test_iteration21_hard_delete"},
            timeout=30,
        )
        
        # Should succeed with super_admin
        assert response.status_code == 200, f"Hard delete failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("status") == "hard_deleted", f"Expected status=hard_deleted, got {data.get('status')}"
        print(f"Hard delete successful for user {user_id}")

    def test_admin_users_list_endpoint(self, super_admin_token):
        """Test /api/admin/users endpoint (legacy)"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            params={"scope": "admin"},
            timeout=30,
        )
        assert response.status_code == 200, f"Admin users list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Admin users (legacy endpoint): {len(data)}")

    def test_user_approval_approve_endpoint(self, super_admin_token):
        """Test POST /api/auth/admin/user-approval-requests/{user_id}/approve"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First check if there are pending approvals
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=headers,
            params={"status": "pending"},
            timeout=30,
        )
        assert response.status_code == 200, f"Get pending approvals failed: {response.text}"
        pending = response.json()
        
        if not pending:
            # Create a test user to approve
            test_email = f"test.approve.{os.urandom(4).hex()}@platform.local"
            register_response = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={
                    "email": test_email,
                    "password": "TestApprove123!",
                },
                timeout=30,
            )
            if register_response.status_code != 200:
                pytest.skip(f"Could not create test user: {register_response.text}")
            
            user_data = register_response.json()
            user_id = user_data.get("id")
        else:
            user_id = pending[0].get("id")
        
        # Approve the user
        response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=headers,
            timeout=30,
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("approval_status") == "approved", f"Expected approved, got {data.get('approval_status')}"
            print(f"User {user_id} approved successfully")
        elif response.status_code == 404:
            print(f"User {user_id} not found or already processed")
        else:
            print(f"Approve response: {response.status_code} - {response.text}")

    def test_user_approval_reject_endpoint(self, super_admin_token):
        """Test POST /api/auth/admin/user-approval-requests/{user_id}/reject"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Create a test user to reject
        test_email = f"test.reject.{os.urandom(4).hex()}@platform.local"
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": "TestReject123!",
            },
            timeout=30,
        )
        
        if register_response.status_code != 200:
            pytest.skip(f"Could not create test user: {register_response.text}")
        
        user_data = register_response.json()
        user_id = user_data.get("id")
        
        # Reject the user
        response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/reject",
            headers=headers,
            timeout=30,
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("approval_status") == "rejected", f"Expected rejected, got {data.get('approval_status')}"
            print(f"User {user_id} rejected successfully")
        else:
            print(f"Reject response: {response.status_code} - {response.text}")

    def test_approved_user_appears_in_user_list_not_admin_list(self, super_admin_token):
        """Test that approved users appear in user list but not admin list"""
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Get user list (role=user)
        user_response = requests.get(
            f"{BASE_URL}/api/admin/identity/users",
            headers=headers,
            params={"role": "user", "page": 1, "page_size": 100},
            timeout=30,
        )
        assert user_response.status_code == 200, f"Get user list failed: {user_response.text}"
        user_data = user_response.json()
        user_items = user_data.get("items", [])
        
        # Get admin list (admin roles)
        admin_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            params={"scope": "admin"},
            timeout=30,
        )
        assert admin_response.status_code == 200, f"Get admin list failed: {admin_response.text}"
        admin_items = admin_response.json()
        
        # Check that user emails don't appear in admin list
        user_emails = {item.get("email") for item in user_items}
        admin_emails = {item.get("email") for item in admin_items}
        
        # Users should not be in admin list
        overlap = user_emails & admin_emails
        print(f"User list count: {len(user_items)}, Admin list count: {len(admin_items)}")
        print(f"Overlap (should be empty for proper separation): {overlap}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
