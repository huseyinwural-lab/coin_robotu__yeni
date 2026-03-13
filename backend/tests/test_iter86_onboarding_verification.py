"""
Iteration 86 - Backend tests for:
1. Registration with full_name + phone in payload
2. Email verification request (POST /api/auth/email-verification/request)
3. Email verification verify (POST /api/auth/email-verification/verify)
4. Onboarding status (GET /api/auth/onboarding-status)
"""
import os
import secrets
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session for API calls"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_user_email():
    """Generate unique test email for registration flow"""
    suffix = secrets.randbelow(100000)
    return f"test_iter86_{suffix}@testmail.com"


class TestRegistrationWithFullNameAndPhone:
    """Test registration endpoint accepts full_name and phone fields"""

    def test_register_with_full_name_and_phone(self, api_client, test_user_email):
        """POST /api/auth/register with full_name and phone fields should succeed"""
        payload = {
            "email": test_user_email,
            "password": "TestPass123!",
            "full_name": "Test User Iter86",
            "phone": "+905551234567"
        }
        response = api_client.post(f"{BASE_URL}/api/auth/register", json=payload)
        
        assert response.status_code in [200, 201], f"Register failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should include user id"
        assert data["email"] == test_user_email, "Email should match"
        assert data["approval_status"] == "pending", "New users should be pending"
        
        print(f"[PASS] Registration with full_name and phone succeeded for {test_user_email}")
        return data

    def test_register_without_optional_fields(self, api_client):
        """POST /api/auth/register without full_name/phone should also work"""
        suffix = secrets.randbelow(100000)
        email = f"test_iter86_minimal_{suffix}@testmail.com"
        payload = {
            "email": email,
            "password": "TestPass456!"
        }
        response = api_client.post(f"{BASE_URL}/api/auth/register", json=payload)
        
        assert response.status_code in [200, 201], f"Register without optional fields failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["email"] == email
        
        print(f"[PASS] Registration without full_name/phone succeeded for {email}")


class TestEmailVerificationRequest:
    """Test POST /api/auth/email-verification/request returns code + expires_at"""

    def test_request_verification_code(self, api_client, test_user_email):
        """Should return verification code and expires_at for registered user"""
        payload = {"email": test_user_email}
        response = api_client.post(f"{BASE_URL}/api/auth/email-verification/request", json=payload)
        
        assert response.status_code == 200, f"Request verification failed: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response should include status"
        assert data["status"] == "code_sent", f"Status should be code_sent, got {data.get('status')}"
        assert "email" in data, "Response should include email"
        assert data["email"] == test_user_email, "Email should match"
        assert "verification_code" in data, "Response should include verification_code (MOCKED)"
        assert "expires_at" in data, "Response should include expires_at"
        assert data["verification_code"] is not None, "Verification code should be provided"
        
        print(f"[PASS] Verification code generated: {data['verification_code']}, expires: {data.get('expires_at')}")
        return data["verification_code"]

    def test_request_verification_for_nonexistent_user(self, api_client):
        """Should return 404 for email not found"""
        payload = {"email": "nonexistent_iter86@testmail.com"}
        response = api_client.post(f"{BASE_URL}/api/auth/email-verification/request", json=payload)
        
        assert response.status_code == 404, f"Should return 404 for nonexistent user, got {response.status_code}"
        print("[PASS] Verification request for nonexistent user returns 404")


class TestEmailVerificationVerify:
    """Test POST /api/auth/email-verification/verify validates code and marks verified"""

    def test_verify_email_with_valid_code(self, api_client, test_user_email):
        """Should verify email when correct code is provided"""
        # First request a new code
        request_payload = {"email": test_user_email}
        request_response = api_client.post(f"{BASE_URL}/api/auth/email-verification/request", json=request_payload)
        assert request_response.status_code == 200, f"Failed to request code: {request_response.text}"
        
        code = request_response.json().get("verification_code")
        assert code is not None, "Verification code should be returned"
        
        # Now verify with the code
        verify_payload = {"email": test_user_email, "code": code}
        verify_response = api_client.post(f"{BASE_URL}/api/auth/email-verification/verify", json=verify_payload)
        
        assert verify_response.status_code == 200, f"Verify failed: {verify_response.text}"
        
        data = verify_response.json()
        assert data["status"] == "verified", f"Status should be verified, got {data.get('status')}"
        assert data["email_verified"] is True, "email_verified should be True"
        
        print(f"[PASS] Email verified successfully for {test_user_email}")

    def test_verify_email_with_invalid_code(self, api_client, test_user_email):
        """Should fail with wrong code"""
        # First request a code to ensure the user exists in verification state
        request_payload = {"email": test_user_email}
        api_client.post(f"{BASE_URL}/api/auth/email-verification/request", json=request_payload)
        
        # Try to verify with wrong code
        verify_payload = {"email": test_user_email, "code": "000000"}
        verify_response = api_client.post(f"{BASE_URL}/api/auth/email-verification/verify", json=verify_payload)
        
        assert verify_response.status_code == 400, f"Should return 400 for invalid code, got {verify_response.status_code}"
        print("[PASS] Verification with invalid code returns 400")


class TestOnboardingStatus:
    """Test GET /api/auth/onboarding-status returns step list and profile metadata"""

    def test_get_onboarding_status(self, api_client, test_user_email):
        """Should return steps list with email_verified status"""
        response = api_client.get(f"{BASE_URL}/api/auth/onboarding-status", params={"email": test_user_email})
        
        assert response.status_code == 200, f"Get onboarding status failed: {response.text}"
        
        data = response.json()
        assert "email" in data, "Response should include email"
        assert data["email"] == test_user_email, "Email should match"
        assert "email_verified" in data, "Response should include email_verified"
        assert "approval_status" in data, "Response should include approval_status"
        assert "is_active" in data, "Response should include is_active"
        assert "steps" in data, "Response should include steps list"
        
        steps = data["steps"]
        assert isinstance(steps, list), "Steps should be a list"
        assert len(steps) >= 3, f"Should have at least 3 steps, got {len(steps)}"
        
        # Verify step structure
        step_keys = [s["key"] for s in steps]
        assert "account_created" in step_keys, "Should have account_created step"
        assert "email_verified" in step_keys, "Should have email_verified step"
        assert "admin_approved" in step_keys, "Should have admin_approved step"
        
        print(f"[PASS] Onboarding status returned with {len(steps)} steps")
        print(f"  - email_verified: {data.get('email_verified')}")
        print(f"  - approval_status: {data.get('approval_status')}")
        print(f"  - full_name: {data.get('full_name')}")
        print(f"  - phone: {data.get('phone')}")
        
        return data

    def test_onboarding_status_for_nonexistent_user(self, api_client):
        """Should return 404 for email not found"""
        response = api_client.get(f"{BASE_URL}/api/auth/onboarding-status", params={"email": "nonexistent_iter86@testmail.com"})
        
        assert response.status_code == 404, f"Should return 404 for nonexistent user, got {response.status_code}"
        print("[PASS] Onboarding status for nonexistent user returns 404")


class TestOnboardingFullFlow:
    """Integration test for full registration + verification + status flow"""

    def test_full_onboarding_flow(self, api_client):
        """Full flow: register with profile data → request code → verify → check status"""
        suffix = secrets.randbelow(100000)
        email = f"test_iter86_fullflow_{suffix}@testmail.com"
        
        # Step 1: Register with full_name and phone
        register_payload = {
            "email": email,
            "password": "FullFlow123!",
            "full_name": "Full Flow Test User",
            "phone": "+901234567890"
        }
        reg_response = api_client.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        assert reg_response.status_code in [200, 201], f"Register failed: {reg_response.text}"
        print(f"[STEP 1] Registered user: {email}")
        
        # Step 2: Check initial onboarding status
        status_response = api_client.get(f"{BASE_URL}/api/auth/onboarding-status", params={"email": email})
        assert status_response.status_code == 200
        initial_status = status_response.json()
        assert initial_status["email_verified"] is False, "Initially email should not be verified"
        print(f"[STEP 2] Initial status - email_verified: {initial_status['email_verified']}")
        
        # Step 3: Request verification code
        request_payload = {"email": email}
        request_response = api_client.post(f"{BASE_URL}/api/auth/email-verification/request", json=request_payload)
        assert request_response.status_code == 200
        code = request_response.json().get("verification_code")
        assert code is not None
        print(f"[STEP 3] Verification code received: {code}")
        
        # Step 4: Verify email with the code
        verify_payload = {"email": email, "code": code}
        verify_response = api_client.post(f"{BASE_URL}/api/auth/email-verification/verify", json=verify_payload)
        assert verify_response.status_code == 200
        assert verify_response.json()["email_verified"] is True
        print("[STEP 4] Email verified successfully")
        
        # Step 5: Check updated onboarding status
        final_status_response = api_client.get(f"{BASE_URL}/api/auth/onboarding-status", params={"email": email})
        assert final_status_response.status_code == 200
        final_status = final_status_response.json()
        assert final_status["email_verified"] is True, "Email should be verified after verification"
        assert final_status["full_name"] == "Full Flow Test User", "full_name should be preserved"
        assert final_status["phone"] == "+901234567890", "phone should be preserved"
        
        # Check step statuses
        steps = final_status["steps"]
        account_created_step = next((s for s in steps if s["key"] == "account_created"), None)
        email_verified_step = next((s for s in steps if s["key"] == "email_verified"), None)
        
        assert account_created_step and account_created_step["done"] is True, "account_created step should be done"
        assert email_verified_step and email_verified_step["done"] is True, "email_verified step should be done"
        
        print(f"[STEP 5] Final status verified:")
        print(f"  - full_name: {final_status.get('full_name')}")
        print(f"  - phone: {final_status.get('phone')}")
        print(f"  - email_verified: {final_status['email_verified']}")
        print(f"  - approval_status: {final_status['approval_status']}")
        
        print("[PASS] Full onboarding flow completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
