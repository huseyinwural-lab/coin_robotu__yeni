# Phase 3 Execution Safety - HTTP API Tests
# Tests the admin kill-switch and execution safety endpoints via HTTP

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://audit-closure-dash.preview.emergentagent.com")

ADMIN_EMAIL = "admin@platform.local"
ADMIN_PASSWORD = "Admin12345!"


_token_cache = {}

def get_admin_token():
    """Authenticate admin user and return token."""
    if "token" in _token_cache:
        return _token_cache["token"]
    
    url = f"{BASE_URL}/api/auth/login"
    response = requests.post(url, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if response.status_code != 200:
        pytest.skip(f"Admin login failed with status {response.status_code}: {response.text}")
    token = response.json().get("access_token") or response.json().get("token")
    _token_cache["token"] = token
    return token


class TestAdminKillSwitchEndpoint:
    """Tests for POST /api/admin/kill-switch"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_admin_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def test_kill_switch_post_sets_trading_disabled(self):
        """Test that POST /api/admin/kill-switch can disable trading."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": False,
            "reason": "test_phase3_http_api_disable",
            "requested_by": "pytest_tester",
            "max_total_exposure": 100.0,
            "max_active_positions": 5,
        }
        response = requests.post(url, json=payload, headers=self.headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("trading_enabled") is False
        assert data.get("reason_code") == "TRADING_DISABLED"
        assert data.get("max_total_exposure") == 100.0
        assert data.get("max_active_positions") == 5

    def test_kill_switch_post_enables_trading(self):
        """Test that POST /api/admin/kill-switch can enable trading."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": True,
            "reason": "test_phase3_http_api_enable",
            "requested_by": "pytest_tester",
            "max_total_exposure": 500.0,
            "max_active_positions": 10,
        }
        response = requests.post(url, json=payload, headers=self.headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("trading_enabled") is True
        assert data.get("reason_code") == "TRADING_ENABLED"
        assert data.get("max_total_exposure") == 500.0
        assert data.get("max_active_positions") == 10

    def test_kill_switch_idempotent_behavior(self):
        """Test that repeated calls with same payload produce idempotent=True."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": False,
            "reason": "test_idempotency",
            "requested_by": "pytest_tester",
            "max_total_exposure": 200.0,
            "max_active_positions": 3,
        }
        
        # First call
        first_response = requests.post(url, json=payload, headers=self.headers)
        assert first_response.status_code == 200
        
        # Second call with same payload
        second_response = requests.post(url, json=payload, headers=self.headers)
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert second_data.get("idempotent") is True

    def test_kill_switch_get_returns_current_state(self):
        """Test GET /api/admin/kill-switch returns current state."""
        # First set a known state
        post_url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": True,
            "reason": "set_known_state",
            "requested_by": "pytest_tester",
            "max_total_exposure": 1000.0,
            "max_active_positions": 20,
        }
        requests.post(post_url, json=payload, headers=self.headers)
        
        # Then get the state
        get_url = f"{BASE_URL}/api/admin/kill-switch"
        response = requests.get(get_url, headers=self.headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trading_enabled" in data
        assert "max_total_exposure" in data
        assert "max_active_positions" in data
        assert "current_total_exposure" in data
        assert "current_active_positions" in data
        assert "reason_code" in data

    def test_kill_switch_requires_admin_auth(self):
        """Test that kill-switch endpoint requires admin authentication."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": False,
            "reason": "unauthenticated_test",
            "requested_by": "hacker",
        }
        response = requests.post(url, json=payload)
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestExecutionSafetyReasonCodes:
    """Tests to verify reason codes are standardized."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_admin_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def test_reason_code_trading_disabled(self):
        """Verify TRADING_DISABLED reason code is returned when trading is disabled."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": False,
            "reason": "reason_code_test",
            "requested_by": "pytest_tester",
        }
        response = requests.post(url, json=payload, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("reason_code") == "TRADING_DISABLED"

    def test_reason_code_trading_enabled(self):
        """Verify TRADING_ENABLED reason code is returned when trading is enabled."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        payload = {
            "trading_enabled": True,
            "reason": "reason_code_test",
            "requested_by": "pytest_tester",
        }
        response = requests.post(url, json=payload, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("reason_code") == "TRADING_ENABLED"


class TestExecutionSafetyStateFields:
    """Tests to verify DB fields exist and are used correctly."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = get_admin_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def test_state_fields_present_in_response(self):
        """Verify required fields are present in kill-switch response."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        response = requests.get(url, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Required fields from Phase3 spec
        required_fields = [
            "trading_enabled",
            "max_total_exposure",
            "max_active_positions",
            "current_total_exposure",
            "current_active_positions",
            "open_positions_count",
            "pending_user_intents_count",
            "pending_runtime_intents_count",
            "reason_code",
            "idempotent",
            "updated_at",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_max_total_exposure_can_be_set(self):
        """Verify max_total_exposure can be set via kill-switch."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        test_value = 123.45
        payload = {
            "trading_enabled": True,
            "reason": "exposure_test",
            "requested_by": "pytest_tester",
            "max_total_exposure": test_value,
        }
        response = requests.post(url, json=payload, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("max_total_exposure") == test_value

    def test_max_active_positions_can_be_set(self):
        """Verify max_active_positions can be set via kill-switch."""
        url = f"{BASE_URL}/api/admin/kill-switch"
        test_value = 7
        payload = {
            "trading_enabled": True,
            "reason": "positions_test",
            "requested_by": "pytest_tester",
            "max_active_positions": test_value,
        }
        response = requests.post(url, json=payload, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("max_active_positions") == test_value


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
