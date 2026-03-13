"""
Iteration 89: Scanner Automation Profiles + User Signals Layout Fix Testing

Features to test:
1. POST/GET/PUT/DELETE /api/user/scanner/automation-profiles CRUD
2. POST /api/user/scanner/automation-profiles/{id}/activate
3. Runtime automation loop profile-based handling (last_run_id, last_run_status, last_actionable_count)
4. Legacy /api/user/scanner/automation endpoint continues to work
"""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "TEST_phase4iter2_pipeline@example.com"
TEST_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def auth_token():
    """Login and get auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Auth failed: {response.status_code} - {response.text}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Requests session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    })
    return session


class TestLegacyScannerAutomationEndpoint:
    """Test legacy /api/user/scanner/automation endpoint still works"""

    def test_get_automation_config_returns_200(self, api_client):
        """GET /api/user/scanner/automation should return 200"""
        response = api_client.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert "user_id" in data
        assert "auto_enabled" in data
        print(f"Legacy automation config: auto_enabled={data.get('auto_enabled')}, interval={data.get('interval_seconds')}")

    def test_put_automation_config_persists(self, api_client):
        """PUT /api/user/scanner/automation should persist config"""
        payload = {
            "auto_enabled": True,
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        response = api_client.put(f"{BASE_URL}/api/user/scanner/automation", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("auto_enabled") == True
        assert data.get("interval_seconds") == 180
        print("Legacy automation config PUT works")


class TestAutomationProfilesCRUD:
    """Test CRUD operations for /api/user/scanner/automation-profiles"""

    def test_list_automation_profiles_returns_200(self, api_client):
        """GET /api/user/scanner/automation-profiles should return list"""
        response = api_client.get(f"{BASE_URL}/api/user/scanner/automation-profiles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} existing automation profiles")

    def test_create_automation_profile_scalp_3m(self, api_client):
        """POST /api/user/scanner/automation-profiles - create scalp-3m profile"""
        payload = {
            "name": f"TEST_scalp_3m_{int(time.time())}",
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("name") == payload["name"]
        assert data.get("auto_enabled") == True
        assert data.get("interval_seconds") == 180
        assert "id" in data
        print(f"Created profile: {data.get('name')} with id={data.get('id')}")
        return data

    def test_create_automation_profile_swing_15m(self, api_client):
        """POST /api/user/scanner/automation-profiles - create swing-15m profile"""
        payload = {
            "name": f"TEST_swing_15m_{int(time.time())}",
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 900,  # 15 minutes
            "max_results": 30,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_100",
            "selected_symbols": [],
        }
        response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("name") == payload["name"]
        assert data.get("interval_seconds") == 900
        print(f"Created profile: {data.get('name')} with interval_seconds={data.get('interval_seconds')}")
        return data

    def test_create_profile_duplicate_name_fails(self, api_client):
        """POST /api/user/scanner/automation-profiles - duplicate name should fail"""
        # First create a profile
        unique_name = f"TEST_duplicate_{int(time.time())}"
        payload1 = {
            "name": unique_name,
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        response1 = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=payload1)
        assert response1.status_code == 200

        # Try to create with same name
        payload2 = {**payload1}
        response2 = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=payload2)
        assert response2.status_code == 400, f"Expected 400 for duplicate name, got {response2.status_code}"
        print("Duplicate name correctly rejected")

    def test_update_automation_profile(self, api_client):
        """PUT /api/user/scanner/automation-profiles/{id} - update profile"""
        # First create a profile
        create_payload = {
            "name": f"TEST_update_{int(time.time())}",
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        create_response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=create_payload)
        assert create_response.status_code == 200
        profile_id = create_response.json().get("id")

        # Update the profile
        update_payload = {
            "name": f"TEST_updated_{int(time.time())}",
            "auto_enabled": False,
            "is_active": False,
            "interval_seconds": 1800,  # 30 minutes
            "max_results": 50,
            "symbol_source": "crypto",
            "symbol_selection_mode": "custom_list",
            "selected_symbols": ["BTCUSDT", "ETHUSDT"],
        }
        update_response = api_client.put(f"{BASE_URL}/api/user/scanner/automation-profiles/{profile_id}", json=update_payload)
        assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
        updated_data = update_response.json()
        assert updated_data.get("auto_enabled") == False
        assert updated_data.get("interval_seconds") == 1800
        assert "BTCUSDT" in updated_data.get("selected_symbols", [])
        print(f"Updated profile: {updated_data.get('name')} with interval_seconds={updated_data.get('interval_seconds')}")

    def test_delete_automation_profile(self, api_client):
        """DELETE /api/user/scanner/automation-profiles/{id} - delete profile"""
        # First create a profile
        create_payload = {
            "name": f"TEST_delete_{int(time.time())}",
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        create_response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=create_payload)
        assert create_response.status_code == 200
        profile_id = create_response.json().get("id")

        # Delete the profile
        delete_response = api_client.delete(f"{BASE_URL}/api/user/scanner/automation-profiles/{profile_id}")
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}: {delete_response.text}"
        delete_data = delete_response.json()
        assert delete_data.get("deleted") == True
        print(f"Deleted profile: {profile_id}")

        # Verify it's gone
        list_response = api_client.get(f"{BASE_URL}/api/user/scanner/automation-profiles")
        profile_ids = [p.get("id") for p in list_response.json()]
        assert profile_id not in profile_ids
        print("Profile deletion verified")

    def test_delete_nonexistent_profile_returns_404(self, api_client):
        """DELETE /api/user/scanner/automation-profiles/{id} - nonexistent should return 404"""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = api_client.delete(f"{BASE_URL}/api/user/scanner/automation-profiles/{fake_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Nonexistent profile delete correctly returns 404")


class TestActivateAutomationProfile:
    """Test profile activation endpoint"""

    def test_activate_automation_profile(self, api_client):
        """POST /api/user/scanner/automation-profiles/{id}/activate - activate profile"""
        # Create two profiles
        profile1_payload = {
            "name": f"TEST_activate_1_{int(time.time())}",
            "auto_enabled": True,
            "is_active": True,  # Make this one active
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        response1 = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=profile1_payload)
        assert response1.status_code == 200
        profile1_id = response1.json().get("id")

        profile2_payload = {
            "name": f"TEST_activate_2_{int(time.time())}",
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 900,
            "max_results": 30,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_100",
            "selected_symbols": [],
        }
        response2 = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=profile2_payload)
        assert response2.status_code == 200
        profile2_id = response2.json().get("id")

        # Activate profile2
        activate_response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles/{profile2_id}/activate")
        assert activate_response.status_code == 200, f"Expected 200, got {activate_response.status_code}: {activate_response.text}"
        activated_data = activate_response.json()
        assert activated_data.get("is_active") == True
        print(f"Activated profile: {activated_data.get('name')}")

        # Verify profile1 is now inactive
        list_response = api_client.get(f"{BASE_URL}/api/user/scanner/automation-profiles")
        profiles = list_response.json()
        for p in profiles:
            if p.get("id") == profile1_id:
                assert p.get("is_active") == False, "First profile should be deactivated"
            if p.get("id") == profile2_id:
                assert p.get("is_active") == True, "Second profile should be active"
        print("Activation correctly switches active profile")

    def test_activate_nonexistent_profile_returns_404(self, api_client):
        """POST /api/user/scanner/automation-profiles/{id}/activate - nonexistent returns 404"""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles/{fake_id}/activate")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Nonexistent profile activation correctly returns 404")


class TestProfileRuntimeFields:
    """Test that runtime fields are updated correctly"""

    def test_profile_has_runtime_fields(self, api_client):
        """Verify profile response contains last_run_id, last_run_status, last_actionable_count"""
        # Create a profile
        create_payload = {
            "name": f"TEST_runtime_{int(time.time())}",
            "auto_enabled": True,
            "is_active": False,
            "interval_seconds": 180,
            "max_results": 25,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        response = api_client.post(f"{BASE_URL}/api/user/scanner/automation-profiles", json=create_payload)
        assert response.status_code == 200
        data = response.json()

        # Verify runtime fields exist
        assert "last_run_id" in data
        assert "last_run_status" in data
        assert "last_actionable_count" in data
        assert "last_run_at" in data
        assert "last_run_error" in data
        assert "next_run_at" in data
        print(f"Profile has all runtime fields: last_run_status={data.get('last_run_status')}, last_actionable_count={data.get('last_actionable_count')}")


class TestScannerRun:
    """Test scanner run still works"""

    def test_scanner_run_returns_200(self, api_client):
        """POST /api/user/scanner/run should return 200"""
        payload = {
            "mode": "ASSISTED",
            "max_results": 10,
            "symbol_source": "crypto",
            "symbol_selection_mode": "top_active_50",
            "selected_symbols": [],
        }
        response = api_client.post(f"{BASE_URL}/api/user/scanner/run", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "run_id" in data
        assert "actionable_count" in data
        print(f"Scanner run: run_id={data.get('run_id')}, actionable_count={data.get('actionable_count')}")


class TestCleanupTestProfiles:
    """Cleanup test profiles after tests"""

    def test_cleanup_test_profiles(self, api_client):
        """Delete all TEST_ prefixed profiles"""
        list_response = api_client.get(f"{BASE_URL}/api/user/scanner/automation-profiles")
        profiles = list_response.json()
        deleted_count = 0
        for profile in profiles:
            name = profile.get("name", "")
            if name.startswith("TEST_"):
                profile_id = profile.get("id")
                delete_response = api_client.delete(f"{BASE_URL}/api/user/scanner/automation-profiles/{profile_id}")
                if delete_response.status_code == 200:
                    deleted_count += 1
        print(f"Cleaned up {deleted_count} test profiles")
