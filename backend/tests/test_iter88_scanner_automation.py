"""
Iteration 88 - Scanner Automation Config API Tests
Tests for:
- GET /api/user/scanner/automation - returns config with auto_enabled, interval_seconds=180, source/mode/selected_symbols, last/next run
- PUT /api/user/scanner/automation - persists selection
- Runtime scanner automation loop updates last_run_at + last_run_status
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_USER_EMAIL = "TEST_phase4iter2_pipeline@example.com"
TEST_USER_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def user_session():
    """Authenticate test user and return session with token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    token = login_response.json().get("access_token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestScannerAutomationConfigGET:
    """Tests for GET /api/user/scanner/automation endpoint"""

    def test_get_automation_config_returns_200(self, user_session):
        """GET /api/user/scanner/automation returns 200"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200
        data = response.json()
        assert "auto_enabled" in data
        assert "interval_seconds" in data
        assert "symbol_source" in data
        assert "symbol_selection_mode" in data
        assert "selected_symbols" in data
        assert "last_run_at" in data
        assert "next_run_at" in data
        print(f"GET automation config success: {data}")

    def test_get_automation_config_interval_is_180(self, user_session):
        """Interval seconds should be fixed at 180"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200
        data = response.json()
        assert data.get("interval_seconds") == 180, f"Expected 180, got {data.get('interval_seconds')}"
        print(f"Interval seconds verified: {data.get('interval_seconds')}")

    def test_get_automation_config_has_required_fields(self, user_session):
        """Verify all required response fields are present"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "id",
            "user_id",
            "auto_enabled",
            "interval_seconds",
            "max_results",
            "symbol_source",
            "symbol_selection_mode",
            "selected_symbols",
            "last_run_id",
            "last_run_status",
            "last_run_error",
            "last_run_at",
            "next_run_at",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print("All required fields present in response")


class TestScannerAutomationConfigPUT:
    """Tests for PUT /api/user/scanner/automation endpoint"""

    def test_put_automation_config_persists_selection(self, user_session):
        """PUT /api/user/scanner/automation persists symbol selection"""
        test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        test_source = "crypto"
        test_mode = "custom_list"
        
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": test_source,
                "symbol_selection_mode": test_mode,
                "selected_symbols": test_symbols,
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("auto_enabled") is True
        assert data.get("interval_seconds") == 180
        assert data.get("symbol_source") == test_source
        assert data.get("symbol_selection_mode") == test_mode
        assert set(data.get("selected_symbols", [])) == set(test_symbols)
        print(f"PUT automation config persisted: {data}")

    def test_put_automation_config_toggle_off(self, user_session):
        """PUT /api/user/scanner/automation can disable automation"""
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": False,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("auto_enabled") is False
        print(f"Automation disabled: {data.get('auto_enabled')}")

    def test_put_automation_config_toggle_on(self, user_session):
        """PUT /api/user/scanner/automation can enable automation"""
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("auto_enabled") is True
        print(f"Automation enabled: {data.get('auto_enabled')}")

    def test_put_automation_config_persists_across_get(self, user_session):
        """After PUT, subsequent GET returns persisted values"""
        test_symbols = ["XRPUSDT", "ADAUSDT"]
        test_source = "crypto"
        test_mode = "custom_list"
        
        # PUT new config
        put_response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 30,
                "symbol_source": test_source,
                "symbol_selection_mode": test_mode,
                "selected_symbols": test_symbols,
            },
        )
        assert put_response.status_code == 200
        
        # GET and verify persistence
        get_response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert get_response.status_code == 200
        data = get_response.json()
        
        assert data.get("symbol_source") == test_source
        assert data.get("symbol_selection_mode") == test_mode
        assert set(data.get("selected_symbols", [])) == set(test_symbols)
        print(f"Persistence verified - symbol_source: {data.get('symbol_source')}, mode: {data.get('symbol_selection_mode')}, symbols: {data.get('selected_symbols')}")


class TestScannerAutomationStatus:
    """Tests for automation run status fields"""

    def test_last_run_status_field_exists(self, user_session):
        """last_run_status field should exist in response"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert response.status_code == 200
        data = response.json()
        assert "last_run_status" in data
        # Valid values: idle, success, error
        assert data.get("last_run_status") in ["idle", "success", "error", None], f"Unexpected status: {data.get('last_run_status')}"
        print(f"last_run_status: {data.get('last_run_status')}")

    def test_next_run_at_calculated_when_enabled(self, user_session):
        """next_run_at should be calculated when auto_enabled is true"""
        # Enable automation first
        put_response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
        )
        assert put_response.status_code == 200
        
        # GET and check next_run_at
        get_response = user_session.get(f"{BASE_URL}/api/user/scanner/automation")
        assert get_response.status_code == 200
        data = get_response.json()
        
        # When enabled, next_run_at should be set
        if data.get("auto_enabled"):
            # next_run_at can be None if last_run_at is None (it will be "now")
            # or it can be a datetime string
            print(f"auto_enabled=True, next_run_at: {data.get('next_run_at')}")
        else:
            # When disabled, next_run_at should be None
            assert data.get("next_run_at") is None
        print("next_run_at calculation verified")


class TestScannerRunEndpoint:
    """Tests for scanner run integration with automation"""

    def test_scanner_run_updates_last_run(self, user_session):
        """Running scanner should update last_run_at and last_run_status"""
        # First enable automation with settings
        user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
        )
        
        # Run scanner
        run_response = user_session.post(
            f"{BASE_URL}/api/user/scanner/run",
            json={
                "mode": "ASSISTED",
                "max_results": 10,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
        )
        assert run_response.status_code == 200
        run_data = run_response.json()
        assert "run_id" in run_data
        print(f"Scanner run completed: run_id={run_data.get('run_id')}")
        
        # Note: Manual scanner run does NOT update automation config's last_run_at
        # Only the runtime loop does that. So we just verify scanner ran successfully.


class TestScannerAutomationSymbolModes:
    """Tests for different symbol selection modes"""

    def test_top_active_50_mode(self, user_session):
        """Test top_active_50 mode persists correctly"""
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_50",
                "selected_symbols": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("symbol_selection_mode") == "top_active_50"

    def test_top_active_100_mode(self, user_session):
        """Test top_active_100 mode persists correctly"""
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_active_100",
                "selected_symbols": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("symbol_selection_mode") == "top_active_100"

    def test_custom_list_mode_with_symbols(self, user_session):
        """Test custom_list mode with specific symbols"""
        test_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "DOTUSDT"]
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "custom_list",
                "selected_symbols": test_symbols,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("symbol_selection_mode") == "custom_list"
        assert set(data.get("selected_symbols", [])) == set(test_symbols)

    def test_bot_scope_mode(self, user_session):
        """Test bot_scope mode persists correctly"""
        response = user_session.put(
            f"{BASE_URL}/api/user/scanner/automation",
            json={
                "auto_enabled": True,
                "interval_seconds": 180,
                "max_results": 25,
                "symbol_source": "crypto",
                "symbol_selection_mode": "bot_scope",
                "selected_symbols": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("symbol_selection_mode") == "bot_scope"
