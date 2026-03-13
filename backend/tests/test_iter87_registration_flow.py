"""
Iteration 87 - Registration Flow Tests
Tests for:
1. POST /api/auth/register with first_name + last_name + phone payload
2. GET /api/auth/onboarding-status returns full_name = first_name + last_name
3. Admin sidebar scroll functionality (tested via UI)
"""

import os
import random
import string
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

def random_suffix():
    return "".join(random.choices(string.digits, k=5))


class TestRegistrationWithFirstLastName:
    """Tests for POST /api/auth/register with first_name + last_name + phone"""

    def test_register_with_first_name_last_name_phone(self):
        """Test registration with first_name, last_name, and phone fields"""
        suffix = random_suffix()
        email = f"test_iter87_reg_{suffix}@testmail.com"
        
        payload = {
            "email": email,
            "password": "TestPassword123!",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+1234567890"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        print(f"Register response status: {response.status_code}")
        print(f"Register response body: {response.text}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "id" in data, "Response should contain user id"
        assert data.get("email") == email, "Email should match"

    def test_register_with_first_name_last_name_without_phone(self):
        """Test registration with first_name and last_name but without phone"""
        suffix = random_suffix()
        email = f"test_iter87_nophone_{suffix}@testmail.com"
        
        payload = {
            "email": email,
            "password": "TestPassword123!",
            "first_name": "Jane",
            "last_name": "Smith"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        print(f"Register response status: {response.status_code}")
        print(f"Register response body: {response.text}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "id" in data, "Response should contain user id"

    def test_register_with_first_name_only(self):
        """Test registration with only first_name (no last_name)"""
        suffix = random_suffix()
        email = f"test_iter87_firstonly_{suffix}@testmail.com"
        
        payload = {
            "email": email,
            "password": "TestPassword123!",
            "first_name": "Solo"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
        print(f"Register response status: {response.status_code}")
        print(f"Register response body: {response.text}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


class TestOnboardingStatusFullName:
    """Tests for GET /api/auth/onboarding-status with full_name as first+last"""

    def test_onboarding_status_shows_combined_full_name(self):
        """Test that onboarding status shows full_name as first_name + last_name"""
        suffix = random_suffix()
        email = f"test_iter87_onboard_{suffix}@testmail.com"
        
        # First register a user with first_name and last_name
        register_payload = {
            "email": email,
            "password": "TestPassword123!",
            "first_name": "FirstTest",
            "last_name": "LastTest",
            "phone": "+9876543210"
        }
        
        reg_response = requests.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
        
        # Now check onboarding status
        status_response = requests.get(f"{BASE_URL}/api/auth/onboarding-status?email={email}")
        print(f"Onboarding status response: {status_response.status_code}")
        print(f"Onboarding status body: {status_response.text}")
        
        assert status_response.status_code == 200, f"Expected 200, got {status_response.status_code}"
        data = status_response.json()
        
        # Verify full_name is the combination of first_name + last_name
        expected_full_name = "FirstTest LastTest"
        actual_full_name = data.get("full_name")
        assert actual_full_name == expected_full_name, f"Expected full_name '{expected_full_name}', got '{actual_full_name}'"
        
        # Verify phone is stored
        assert data.get("phone") == "+9876543210", f"Phone mismatch: {data.get('phone')}"
        
        # Verify steps structure
        steps = data.get("steps", [])
        assert len(steps) > 0, "Steps should not be empty"
        step_keys = [s.get("key") for s in steps]
        assert "account_created" in step_keys, "Should have account_created step"
        assert "email_verified" in step_keys, "Should have email_verified step"

    def test_onboarding_status_with_first_name_only(self):
        """Test onboarding status when only first_name is provided"""
        suffix = random_suffix()
        email = f"test_iter87_firstonly_onboard_{suffix}@testmail.com"
        
        # Register with only first_name
        register_payload = {
            "email": email,
            "password": "TestPassword123!",
            "first_name": "OnlyFirst"
        }
        
        reg_response = requests.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
        
        # Check onboarding status
        status_response = requests.get(f"{BASE_URL}/api/auth/onboarding-status?email={email}")
        assert status_response.status_code == 200, f"Expected 200, got {status_response.status_code}"
        data = status_response.json()
        
        # full_name should be just the first_name (no trailing space)
        actual_full_name = data.get("full_name")
        assert actual_full_name == "OnlyFirst", f"Expected 'OnlyFirst', got '{actual_full_name}'"


class TestAdminLogin:
    """Test admin login for sidebar scroll verification"""

    def test_admin_login_success(self):
        """Test admin can login successfully"""
        login_payload = {
            "email": "admin@platform.dev",
            "password": "Admin12345!"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/login/admin", json=login_payload)
        print(f"Admin login response: {response.status_code}")
        
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Should receive access_token"
        assert data.get("user", {}).get("role") in ["admin", "super_admin", "ops"], "Should be admin role"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
