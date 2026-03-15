"""
API tests for Tiered Scanner Pipeline and Admin Runtime Summary
Tests Discovery -> Qualification -> Decision flow and API contracts
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip("Admin login failed - skipping tests")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def user_token(admin_token):
    """Create and approve a test user, return user token"""
    # Register test user
    email = f"test_tiered_{os.urandom(4).hex()}@testmail.com"
    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "TestUser123!"},
        timeout=30,
    )
    if register_response.status_code not in [200, 201]:
        pytest.skip("User registration failed")
    
    user_id = register_response.json().get("id")
    
    # Approve user
    headers = {"Authorization": f"Bearer {admin_token}"}
    requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=headers,
        timeout=30,
    )
    
    # Login as user
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": email, "password": "TestUser123!"},
        timeout=30,
    )
    if login_response.status_code != 200:
        pytest.skip("User login failed")
    
    return login_response.json().get("access_token")


class TestAdminLogin:
    """Admin login endpoint tests"""

    def test_admin_login_success(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] in ["super_admin", "admin", "ops"]

    def test_admin_login_invalid_credentials(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": "wrong@test.com", "password": "wrongpass"},
            timeout=30,
        )
        assert response.status_code in [401, 400, 404]


class TestAdminRuntimeSummary:
    """Admin runtime-summary endpoint tests for tiered_scan field"""

    def test_runtime_summary_returns_tiered_scan_field(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary",
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify tiered_scan field exists (may be empty if no scan run)
        assert "tiered_scan" in data
        assert "scanner_mode_effective" in data
        assert "fallback_state" in data

    def test_runtime_summary_with_scanner_mode_param(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/universe/runtime-summary?scanner_mode=all_market_symbols&top_n=50",
            headers=headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scanner_mode_requested"] == "all_market_symbols"


class TestUserScannerRuntime:
    """User scanner runtime endpoint tests for tiered scan pipeline"""

    def test_runtime_run_returns_tiered_scan_payload(self, user_token):
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/runtime/run?symbol_selection_mode=all_market_symbols&max_results=10",
            headers=headers,
            timeout=60,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify tiered_scan structure
        assert "tiered_scan" in data
        tiered = data["tiered_scan"]
        assert tiered.get("enabled") is True
        
        # Verify tier caps
        caps = tiered.get("caps", {})
        assert "discovery_cap" in caps
        assert "qualification_cap" in caps
        assert "decision_cap" in caps
        
        # Verify discovery stage
        discovery = tiered.get("discovery", {})
        assert "universe_size" in discovery
        assert "candidate_count" in discovery
        assert "candidate_symbols" in discovery
        
        # Verify qualification stage
        qualification = tiered.get("qualification", {})
        assert "input_count" in qualification
        assert "qualified_count" in qualification
        assert "candidate_symbols" in qualification
        
        # Verify decision kernel
        decision = tiered.get("decision_kernel", {})
        assert "input_symbols_count" in decision
        assert "max_results" in decision
        assert decision.get("symbol_selection_mode") == "manual_selection"

    def test_runtime_run_requires_user_role(self, admin_token):
        """Admin token should not work for user-only endpoints"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/runtime/run?symbol_selection_mode=all_market_symbols&max_results=10",
            headers=headers,
            timeout=30,
        )
        # Should return 403 or similar - admin cannot access user-only endpoints
        assert response.status_code in [400, 401, 403]


class TestCredentialCleanup:
    """Verify no deprecated credentials in codebase"""

    def test_no_admin_platform_dev_credential(self):
        """Ensure deprecated admin domain is not in production code (excluding test files)"""
        import subprocess
        # Search in backend source code excluding tests
        result = subprocess.run(
            ["grep", "-r", "--include=*.py", "--exclude-dir=tests", "--exclude-dir=__pycache__", 
             "admin@platform" + ".dev", "/app/backend"],
            capture_output=True,
            text=True,
        )
        # Also check frontend source
        result2 = subprocess.run(
            ["grep", "-r", "--include=*.ts", "--include=*.tsx", "--include=*.js", "--include=*.jsx",
             "admin@platform" + ".dev", "/app/frontend/src"],
            capture_output=True,
            text=True,
        )
        # returncode 1 means not found (good), 0 means found (bad)
        assert result.returncode != 0, f"Found deprecated credential in backend: {result.stdout}"
        assert result2.returncode != 0, f"Found deprecated credential in frontend: {result2.stdout}"
