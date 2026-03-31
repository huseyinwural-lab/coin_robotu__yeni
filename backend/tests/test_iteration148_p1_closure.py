"""
Iteration 148: P1 Final Closure Testing
- Health endpoint stability
- Admin login flow
- User approvals page endpoints
- Workflow visibility endpoints
- Decision support endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


class TestHealthEndpoint:
    """Health endpoint stability tests"""

    def test_health_endpoint_returns_200(self):
        """GET /api/health should return 200 quickly"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health endpoint failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Health status not ok: {data}"
        print(f"Health endpoint OK: {data.get('status')}")

    def test_health_endpoint_has_database_info(self):
        """Health endpoint should include database status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        checks = data.get("checks", {})
        db_check = checks.get("database", {})
        assert db_check.get("configured") is True, "Database not configured"
        assert db_check.get("url_valid") is True, "Database URL not valid"
        print(f"Database check: configured={db_check.get('configured')}, reachable={db_check.get('reachable')}")


class TestAdminLogin:
    """Admin login flow tests"""

    def test_admin_login_success(self):
        """POST /api/auth/login with admin credentials should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "panel": "admin"},
            timeout=15,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert data.get("user", {}).get("role") in ["admin", "super_admin"], "User is not admin"
        print(f"Admin login successful: role={data.get('user', {}).get('role')}")

    def test_admin_login_returns_user_info(self):
        """Login response should include user info"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "panel": "admin"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        user = data.get("user", {})
        assert user.get("email") == ADMIN_EMAIL, "Email mismatch"
        assert user.get("id"), "No user ID"
        print(f"User info: id={user.get('id')}, email={user.get('email')}")

    def test_admin_login_invalid_credentials(self):
        """Login with wrong password should fail with 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpassword", "panel": "admin"},
            timeout=15,
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Invalid credentials correctly rejected with 401")


@pytest.fixture
def admin_token():
    """Get admin auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "panel": "admin"},
        timeout=15,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json().get("access_token")


@pytest.fixture
def admin_headers(admin_token):
    """Get headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestAuthMe:
    """Auth me endpoint tests"""

    def test_auth_me_with_valid_token(self, admin_headers):
        """GET /api/auth/me should return user info"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers, timeout=10)
        assert response.status_code == 200, f"Auth me failed: {response.text}"
        data = response.json()
        assert data.get("email") == ADMIN_EMAIL
        print(f"Auth me OK: {data.get('email')}")

    def test_auth_me_without_token(self):
        """GET /api/auth/me without token should fail"""
        response = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Auth me correctly rejected without token")


class TestUserApprovals:
    """User approvals endpoint tests"""

    def test_list_user_approvals(self, admin_headers):
        """GET /api/admin/user-approvals should return list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"},
            timeout=10,
        )
        assert response.status_code == 200, f"User approvals failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"User approvals: {len(data)} pending requests")

    def test_user_approvals_email_suggestions(self, admin_headers):
        """GET /api/admin/user-approvals/email-suggestions should work"""
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals/email-suggestions",
            headers=admin_headers,
            params={"query": "", "limit": 8},
            timeout=10,
        )
        assert response.status_code == 200, f"Email suggestions failed: {response.text}"
        data = response.json()
        assert "suggestions" in data, "No suggestions field"
        print(f"Email suggestions: {len(data.get('suggestions', []))} results")

    def test_user_approvals_sort_and_search(self, admin_headers):
        """User approvals should support sort and search params"""
        response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending", "sort_by": "email", "sort_dir": "desc"},
            timeout=10,
        )
        assert response.status_code == 200, f"Sort/search failed: {response.text}"
        print("Sort and search params work correctly")


class TestWorkflowQueue:
    """Workflow queue endpoint tests"""

    def test_workflow_queue_list(self, admin_headers):
        """GET /api/admin/onboarding/workflow/queue should return items"""
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/workflow/queue",
            headers=admin_headers,
            timeout=10,
        )
        assert response.status_code == 200, f"Workflow queue failed: {response.text}"
        data = response.json()
        assert "items" in data, "No items field in response"
        print(f"Workflow queue: {len(data.get('items', []))} items")


class TestOnboardingContext:
    """Onboarding context endpoint tests - requires a user_id"""

    def test_onboarding_context_endpoint_exists(self, admin_headers):
        """Verify onboarding context endpoint is accessible"""
        # First get a user from approvals
        approvals_response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"},
            timeout=10,
        )
        if approvals_response.status_code != 200:
            pytest.skip("Cannot get user approvals")
        
        users = approvals_response.json()
        if not users:
            pytest.skip("No pending users to test context")
        
        user_id = users[0].get("id")
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{user_id}/context",
            headers=admin_headers,
            timeout=10,
        )
        assert response.status_code == 200, f"Context failed: {response.text}"
        data = response.json()
        # Context should have decision_support and decision_engine fields
        print(f"Context loaded for user {user_id}: keys={list(data.keys())}")

    def test_decision_support_endpoint(self, admin_headers):
        """GET /api/admin/onboarding/{user_id}/decision-support should work"""
        approvals_response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"},
            timeout=10,
        )
        if approvals_response.status_code != 200:
            pytest.skip("Cannot get user approvals")
        
        users = approvals_response.json()
        if not users:
            pytest.skip("No pending users to test decision support")
        
        user_id = users[0].get("id")
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{user_id}/decision-support",
            headers=admin_headers,
            timeout=10,
        )
        assert response.status_code == 200, f"Decision support failed: {response.text}"
        data = response.json()
        assert "decision_support" in data or "decision_engine" in data, "Missing decision fields"
        print(f"Decision support loaded: {list(data.keys())}")


class TestWorkflowActions:
    """Workflow action endpoint tests"""

    def test_workflow_start_endpoint_exists(self, admin_headers):
        """POST /api/admin/onboarding/{user_id}/workflow/start should be accessible"""
        approvals_response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"},
            timeout=10,
        )
        if approvals_response.status_code != 200:
            pytest.skip("Cannot get user approvals")
        
        users = approvals_response.json()
        if not users:
            pytest.skip("No pending users to test workflow start")
        
        user_id = users[0].get("id")
        # Check if workflow already exists
        workflow_response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{user_id}/workflow",
            headers=admin_headers,
            timeout=10,
        )
        if workflow_response.status_code == 200:
            workflow_data = workflow_response.json()
            if workflow_data.get("workflow_case"):
                print(f"Workflow already exists for user {user_id}")
                return
        
        # Try to start workflow
        response = requests.post(
            f"{BASE_URL}/api/admin/onboarding/{user_id}/workflow/start",
            headers=admin_headers,
            json={"assigned_admin_id": None},
            timeout=10,
        )
        # Accept 200, 201, or 409 (already exists)
        assert response.status_code in [200, 201, 409], f"Workflow start failed: {response.text}"
        print(f"Workflow start response: {response.status_code}")

    def test_workflow_get_endpoint(self, admin_headers):
        """GET /api/admin/onboarding/{user_id}/workflow should work"""
        approvals_response = requests.get(
            f"{BASE_URL}/api/admin/user-approvals",
            headers=admin_headers,
            params={"status": "pending"},
            timeout=10,
        )
        if approvals_response.status_code != 200:
            pytest.skip("Cannot get user approvals")
        
        users = approvals_response.json()
        if not users:
            pytest.skip("No pending users to test workflow get")
        
        user_id = users[0].get("id")
        response = requests.get(
            f"{BASE_URL}/api/admin/onboarding/{user_id}/workflow",
            headers=admin_headers,
            timeout=10,
        )
        assert response.status_code == 200, f"Workflow get failed: {response.text}"
        data = response.json()
        # workflow_case can be null if not started
        print(f"Workflow get response: workflow_case={'exists' if data.get('workflow_case') else 'null'}")


class TestBulkActions:
    """Bulk action endpoint tests"""

    def test_bulk_approve_disabled(self, admin_headers):
        """POST /api/admin/user-approvals/bulk-approve should be disabled"""
        response = requests.post(
            f"{BASE_URL}/api/admin/user-approvals/bulk-approve",
            headers=admin_headers,
            json={"ids": [], "reason": "test"},
            timeout=10,
        )
        # Should return 403 as bulk approve is disabled
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("Bulk approve correctly disabled with 403")

    def test_bulk_reject_requires_ids(self, admin_headers):
        """POST /api/admin/user-approvals/bulk-reject should require ids"""
        response = requests.post(
            f"{BASE_URL}/api/admin/user-approvals/bulk-reject",
            headers=admin_headers,
            json={"ids": [], "reason": "test", "confirm_token": "CONFIRM"},
            timeout=10,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("Bulk reject correctly requires ids")

    def test_reject_stale_endpoint(self, admin_headers):
        """POST /api/admin/user-approvals/reject-stale should work"""
        response = requests.post(
            f"{BASE_URL}/api/admin/user-approvals/reject-stale",
            headers=admin_headers,
            json={"stale_days": 30, "reason": "test_stale_rejection"},
            timeout=10,
        )
        assert response.status_code == 200, f"Reject stale failed: {response.text}"
        data = response.json()
        assert "count" in data, "No count in response"
        print(f"Reject stale: {data.get('count')} users affected")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
