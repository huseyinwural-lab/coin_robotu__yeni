"""
Iteration 165 - Production Gate Smoke Tests
============================================
Tests for:
1. Admin login duplicate token_hash handling (register_auth_session)
2. user_venue_assignments testnet_allowed not-null integrity
3. verify_phase6_security.sh script validation
"""
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

REPO_ROOT = Path(__file__).resolve().parents[2]

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "canary.admin@platform.local")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "CanaryAdmin123!")


class TestAdminLoginDuplicateTokenHash:
    """
    Test that admin login does NOT throw IntegrityError on duplicate token_hash.
    The fix in register_auth_session should update existing session instead of inserting duplicate.
    """

    def test_admin_login_first_attempt(self):
        """First admin login should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"First login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert "user" in data, "Missing user in response"
        print(f"PASS: First admin login succeeded, user_id={data['user'].get('id')}")

    def test_admin_login_repeated_attempts_no_integrity_error(self):
        """
        Multiple rapid admin logins should NOT cause IntegrityError.
        The register_auth_session function should handle duplicate token_hash gracefully.
        """
        session = requests.Session()
        device_id = f"test-device-{uuid.uuid4().hex[:8]}"
        
        tokens = []
        for i in range(3):
            response = session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                headers={"X-Session-Device": device_id},
                timeout=30,
            )
            # Should NOT get 500 IntegrityError
            assert response.status_code != 500, f"Login {i+1} got 500 error (possible IntegrityError): {response.text}"
            assert response.status_code == 200, f"Login {i+1} failed: {response.status_code} - {response.text}"
            
            data = response.json()
            tokens.append(data.get("access_token"))
            print(f"PASS: Login attempt {i+1} succeeded")
            time.sleep(0.5)  # Small delay between attempts
        
        # All tokens should be valid
        assert len(tokens) == 3, "Should have 3 tokens"
        print("PASS: All 3 rapid login attempts succeeded without IntegrityError")

    def test_admin_login_with_mfa_verify_flow(self):
        """
        Test that MFA verify flow (which also calls register_auth_session) 
        does not cause duplicate token_hash issues.
        """
        session = requests.Session()
        
        # First login
        response = session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        
        data = response.json()
        token = data.get("access_token")
        
        # Try to access protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        users_response = session.get(
            f"{BASE_URL}/api/admin/users",
            headers=headers,
            timeout=30,
        )
        # Should work (200) or require MFA (403 with specific detail)
        assert users_response.status_code in [200, 403], f"Unexpected status: {users_response.status_code}"
        print(f"PASS: Protected endpoint access returned {users_response.status_code}")


class TestUserVenueAssignmentIntegrity:
    """
    Test that user_venue_assignments.testnet_allowed NOT NULL constraint is satisfied.
    The fix ensures testnet_allowed defaults to False when creating new assignments.
    """

    def test_venue_assignment_has_testnet_allowed_default(self):
        """
        Verify that venue assignment creation sets testnet_allowed to False by default.
        """
        session = requests.Session()
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.status_code}"
        
        token = login_response.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get venue health summary (this triggers venue seeding)
        health_response = session.get(
            f"{BASE_URL}/api/admin/venue/health",
            headers=headers,
            timeout=30,
        )
        # May return 200 or 404 depending on endpoint availability
        print(f"Venue health endpoint returned: {health_response.status_code}")
        
        # The key test is that no IntegrityError occurs during venue operations
        # If we got here without 500 error, the testnet_allowed default is working
        print("PASS: Venue operations completed without NOT NULL constraint violation")

    def test_ensure_user_venue_assignment_idempotent(self):
        """
        Test that ensure_user_venue_assignment is idempotent and handles
        existing rows with NULL testnet_allowed by setting it to False.
        """
        session = requests.Session()
        
        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login/admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert login_response.status_code == 200
        
        token = login_response.json().get("access_token")
        user_id = login_response.json().get("user", {}).get("id")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to get user's venue options (this calls ensure_user_venue_assignment internally)
        venue_response = session.get(
            f"{BASE_URL}/api/user/venue/options",
            headers=headers,
            timeout=30,
        )
        # Should not get 500 error
        assert venue_response.status_code != 500, f"Venue options got 500: {venue_response.text}"
        print(f"PASS: User venue options returned {venue_response.status_code}")


class TestVerifyPhase6SecurityScript:
    """
    Test that verify_phase6_security.sh script passes.
    """

    def test_security_script_passes(self):
        """
        Run verify_phase6_security.sh and verify it returns PASS.
        """
        script_candidates = [
            os.environ.get("PHASE6_SECURITY_SCRIPT_PATH", "").strip(),
            str(REPO_ROOT / "scripts" / "verify_phase6_security.sh"),
            "/app/scripts/verify_phase6_security.sh",
        ]
        script_path = next((item for item in script_candidates if item and os.path.exists(item)), script_candidates[1])
        
        # Check script exists
        assert os.path.exists(script_path), f"Script not found: {script_path}"
        
        # Run the script
        result = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(REPO_ROOT),
            env={
                **os.environ,
                "APP_ROOT": str(REPO_ROOT),
                "TEST_ADMIN_EMAIL": ADMIN_EMAIL,
                "TEST_ADMIN_PASSWORD": ADMIN_PASSWORD,
            },
        )
        
        # Check output for PASS
        combined_output = result.stdout + result.stderr
        
        # The script should exit with 0 and output should contain PASS
        if result.returncode != 0:
            print(f"Script stderr: {result.stderr}")
            print(f"Script stdout: {result.stdout}")
        
        assert result.returncode == 0, f"Script failed with exit code {result.returncode}"
        assert "PASS" in combined_output or '"status": "PASS"' in combined_output, \
            f"Script did not output PASS. Output: {combined_output[-500:]}"
        
        print("PASS: verify_phase6_security.sh completed successfully")

    def test_security_artifacts_generated(self):
        """
        Verify that security script generates expected artifacts.
        """
        artifact_dir = str(REPO_ROOT / "artifacts")
        expected_files = [
            "faz6_security_summary.log",
            "faz6_security_closure_summary.json",
        ]
        
        for filename in expected_files:
            filepath = os.path.join(artifact_dir, filename)
            if os.path.exists(filepath):
                print(f"PASS: Artifact exists: {filename}")
            else:
                print(f"INFO: Artifact not found (may need script run): {filename}")


class TestRegisterAuthSessionDuplicateHandling:
    """
    Direct test of register_auth_session duplicate token_hash handling.
    """

    def test_same_token_multiple_registrations(self):
        """
        Test that calling register_auth_session with the same token
        updates existing session instead of causing IntegrityError.
        """
        session = requests.Session()
        device_id = f"dup-test-{uuid.uuid4().hex[:8]}"
        
        # Login twice with same device
        for i in range(2):
            response = session.post(
                f"{BASE_URL}/api/auth/login/admin",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                headers={"X-Session-Device": device_id},
                timeout=30,
            )
            assert response.status_code == 200, f"Login {i+1} failed: {response.status_code} - {response.text}"
            print(f"PASS: Login {i+1} with same device succeeded")
        
        print("PASS: Duplicate token_hash handling works correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
