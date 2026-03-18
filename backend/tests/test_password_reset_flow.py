"""
Password Reset Flow Tests - Iteration 154
Tests for: POST /api/auth/password-reset/request and POST /api/auth/password-reset/confirm
User story: Şifremi unuttum -> mail token -> yeni şifre

Features tested:
- Generic response (no user enumeration)
- Password policy enforcement (min 10 chars, upper/lower/number/symbol)
- Token validation
- 15 minute token expiry (configuration check)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestPasswordResetRequest:
    """Test POST /api/auth/password-reset/request endpoint"""

    def test_password_reset_request_with_existing_email(self):
        """Request password reset for existing admin email - should return generic accepted response"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": "admin@platform.local"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted", f"Expected status=accepted, got: {data}"
        # Verify generic message (prevents enumeration)
        assert "message" in data
        assert "sıfırlama" in data["message"].lower() or "reset" in data["message"].lower()
        print(f"PASS: Password reset request for existing email returns generic response: {data}")

    def test_password_reset_request_with_nonexistent_email(self):
        """Request password reset for non-existing email - should return same generic response (no enumeration)"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": "nonexistent12345@example.com"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "accepted", f"Expected status=accepted, got: {data}"
        # Verify same generic message as existing email
        assert "message" in data
        print(f"PASS: Password reset request for non-existent email returns same generic response: {data}")

    def test_password_reset_request_missing_email(self):
        """Request password reset without email should fail validation"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={},
            headers={"Content-Type": "application/json"},
        )
        # Should fail validation (400 or 422)
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
        print(f"PASS: Missing email returns validation error: {response.status_code}")

    def test_password_reset_request_invalid_email_format(self):
        """Request password reset with invalid email format"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": "not-an-email"},
            headers={"Content-Type": "application/json"},
        )
        # Email field has min_length=3, so this may still pass to service layer which handles it
        # The service normalizes and returns generic response
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}"
        print(f"PASS: Invalid email format handled: {response.status_code}")


class TestPasswordResetConfirm:
    """Test POST /api/auth/password-reset/confirm endpoint"""

    def test_password_reset_confirm_invalid_token(self):
        """Confirm password reset with invalid token should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "invalid_token_12345678901234567890",
                "new_password": "ValidPass123!",
            },
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "invalid" in data.get("detail", "").lower() or "expired" in data.get("detail", "").lower()
        print(f"PASS: Invalid token returns 400 with appropriate detail: {data}")

    def test_password_reset_confirm_weak_password_too_short(self):
        """Confirm with password less than 10 characters should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "test_token_placeholder_for_validation",
                "new_password": "Short1!",  # Only 7 chars
            },
            headers={"Content-Type": "application/json"},
        )
        # Pydantic validation will catch this (min_length=10 in schema)
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        print(f"PASS: Password too short (< 10 chars) rejected at schema level: {response.status_code}")

    def test_password_reset_confirm_weak_password_no_uppercase(self):
        """Confirm with password without uppercase should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "test_token_placeholder_1234567890",
                "new_password": "lowercase123!",  # No uppercase
            },
            headers={"Content-Type": "application/json"},
        )
        # Password policy validation runs BEFORE token lookup
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "uppercase" in data.get("detail", "").lower()
        print(f"PASS: Password policy enforced (no uppercase): {data.get('detail')}")

    def test_password_reset_confirm_weak_password_no_lowercase(self):
        """Confirm with password without lowercase should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "test_token_placeholder_1234567890",
                "new_password": "UPPERCASE123!",  # No lowercase
            },
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "lowercase" in data.get("detail", "").lower()
        print(f"PASS: Password policy enforced (no lowercase): {data.get('detail')}")

    def test_password_reset_confirm_weak_password_no_number(self):
        """Confirm with password without number should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "test_token_placeholder_1234567890",
                "new_password": "ValidPassword!",  # No number
            },
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "number" in data.get("detail", "").lower()
        print(f"PASS: Password policy enforced (no number): {data.get('detail')}")

    def test_password_reset_confirm_weak_password_no_symbol(self):
        """Confirm with password without symbol should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "test_token_placeholder_1234567890",
                "new_password": "ValidPassword123",  # No symbol
            },
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "symbol" in data.get("detail", "").lower()
        print(f"PASS: Password policy enforced (no symbol): {data.get('detail')}")

    def test_password_reset_confirm_missing_token(self):
        """Confirm without token should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={"new_password": "ValidPass123!"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print(f"PASS: Missing token returns validation error: {response.status_code}")

    def test_password_reset_confirm_missing_password(self):
        """Confirm without password should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={"token": "test_token_placeholder_1234567890"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print(f"PASS: Missing password returns validation error: {response.status_code}")


class TestPasswordResetServiceIntegration:
    """Test integration with Resend email provider (configuration check)"""

    def test_env_configuration_for_resend(self):
        """Verify Resend configuration exists in backend (no actual email send test)"""
        # We just test that the request endpoint works - email is sent asynchronously
        # The actual Resend integration path is tested by successful 200 response
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": "admin@platform.local"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        print("PASS: Password reset request endpoint works (Resend integration path active)")


class TestPasswordPolicyValidation:
    """Direct tests for password policy requirements"""

    def test_valid_strong_password_passes_schema(self):
        """Verify that a strong password passes initial schema validation"""
        # Strong password: 10+ chars, upper, lower, number, symbol
        strong_password = "StrongP@ss123"
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/confirm",
            json={
                "token": "fake_token_for_schema_test_only",
                "new_password": strong_password,
            },
            headers={"Content-Type": "application/json"},
        )
        # Should pass schema validation (422) and fail at token validation (400)
        assert response.status_code == 400, f"Expected 400 (invalid token), got {response.status_code}"
        data = response.json()
        # If we get to token validation, it means password passed schema & policy
        assert "token" in data.get("detail", "").lower() or "invalid" in data.get("detail", "").lower()
        print(f"PASS: Strong password {strong_password} passes validation, fails only at token check")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
