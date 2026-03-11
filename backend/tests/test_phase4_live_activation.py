"""
Phase-4 Controlled Live Activation - Backend API Tests
Tests: testnet connectivity, permission-check, live-config safety enforcement, readiness-check
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL env var required"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestPhase4TestnetConnectivity:
    """GET /api/phase4/testnet-connectivity tests"""

    def test_testnet_connectivity_returns_200(self, admin_headers):
        """Testnet connectivity endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/testnet-connectivity", headers=admin_headers)
        assert response.status_code == 200

    def test_testnet_connectivity_response_fields(self, admin_headers):
        """Testnet connectivity should return status/rest_url/ws_url fields"""
        response = requests.get(f"{BASE_URL}/api/phase4/testnet-connectivity", headers=admin_headers)
        data = response.json()
        
        assert "status" in data
        assert "rest_url" in data
        assert "ws_url" in data
        assert "message" in data
        
        # Validate expected values
        assert data["rest_url"] == "https://testnet.binancefuture.com"
        assert data["ws_url"] == "wss://stream.binancefuture.com/ws"
        assert data["status"] in ["reachable", "unreachable"]

    def test_testnet_connectivity_requires_admin(self):
        """Testnet connectivity should require admin auth"""
        response = requests.get(f"{BASE_URL}/api/phase4/testnet-connectivity")
        assert response.status_code == 401


class TestPhase4PermissionCheck:
    """POST /api/phase4/permission-check tests"""

    def test_permission_check_empty_credentials_returns_missing(self, admin_headers):
        """Empty key/secret should return missing_credentials status"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/permission-check",
            headers=admin_headers,
            json={"api_key": "", "api_secret": ""},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "missing_credentials"
        assert data["api_key_present"] is False
        assert data["api_secret_present"] is False
        assert data["masked_key"] == "missing"

    def test_permission_check_null_credentials_returns_missing(self, admin_headers):
        """Null key/secret should return missing_credentials status"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/permission-check",
            headers=admin_headers,
            json={"api_key": None, "api_secret": None},
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "missing_credentials"
        assert data["api_key_present"] is False
        assert data["api_secret_present"] is False

    def test_permission_check_fake_credentials_returns_invalid_or_error(self, admin_headers):
        """Fake key/secret should return invalid_credentials or exchange_error, NOT 500"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/permission-check",
            headers=admin_headers,
            json={"api_key": "fakeapikey123456789abcdef", "api_secret": "fakesecret123456789abcdef"},
        )
        # Must not be 500 - graceful handling
        assert response.status_code == 200, f"Should not return 500, got {response.status_code}"
        
        data = response.json()
        assert data["status"] in ["invalid_credentials", "exchange_error", "exchange_unreachable"]
        assert data["api_key_present"] is True
        assert data["api_secret_present"] is True
        assert "message" in data

    def test_permission_check_requires_admin(self):
        """Permission check should require admin auth"""
        response = requests.post(
            f"{BASE_URL}/api/phase4/permission-check",
            json={"api_key": "", "api_secret": ""},
        )
        assert response.status_code == 401


class TestPhase4LiveConfigSafetyEnforcement:
    """PUT /api/phase4/live-config safety limits tests"""

    def test_live_config_get_returns_200(self, admin_headers):
        """GET live-config should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/live-config", headers=admin_headers)
        assert response.status_code == 200

    def test_live_config_clamps_leverage_to_safe_limit(self, admin_headers):
        """Leverage should be clamped to MAX_SAFE_LEVERAGE=1 when safe_mode_enabled"""
        # Try to set leverage to 3 (max allowed by schema)
        payload = {
            "exchange": "binance",
            "market_type": "futures_testnet",
            "safe_mode_enabled": True,
            "live_mode_enabled": False,
            "symbol_whitelist": ["BTCUSDT"],
            "max_position_pct": 0.1,
            "leverage_cap": 3,  # Above safe limit of 1
            "max_trades_per_hour": 6,
            "max_notional_exposure": 150,
            "kill_switch_enabled": False,
            "disable_futures": False,
            "ip_whitelist_ready": False,
            "trading_permission_ready": False,
        }
        response = requests.put(f"{BASE_URL}/api/phase4/live-config", headers=admin_headers, json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["leverage_cap"] == 1, "Leverage should be clamped to 1"

    def test_live_config_clamps_max_position_pct(self, admin_headers):
        """max_position_pct should be clamped to MAX_SAFE_POSITION_PCT=0.1"""
        payload = {
            "exchange": "binance",
            "market_type": "futures_testnet",
            "safe_mode_enabled": True,
            "live_mode_enabled": False,
            "symbol_whitelist": ["BTCUSDT"],
            "max_position_pct": 0.5,  # Above safe limit of 0.1
            "leverage_cap": 1,
            "max_trades_per_hour": 6,
            "max_notional_exposure": 150,
            "kill_switch_enabled": False,
            "disable_futures": False,
            "ip_whitelist_ready": False,
            "trading_permission_ready": False,
        }
        response = requests.put(f"{BASE_URL}/api/phase4/live-config", headers=admin_headers, json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["max_position_pct"] == 0.1, "max_position_pct should be clamped to 0.1"

    def test_live_config_clamps_max_notional_exposure(self, admin_headers):
        """max_notional_exposure should be clamped to MAX_SAFE_NOTIONAL_EXPOSURE=150"""
        payload = {
            "exchange": "binance",
            "market_type": "futures_testnet",
            "safe_mode_enabled": True,
            "live_mode_enabled": False,
            "symbol_whitelist": ["BTCUSDT"],
            "max_position_pct": 0.1,
            "leverage_cap": 1,
            "max_trades_per_hour": 6,
            "max_notional_exposure": 500,  # Above safe limit of 150
            "kill_switch_enabled": False,
            "disable_futures": False,
            "ip_whitelist_ready": False,
            "trading_permission_ready": False,
        }
        response = requests.put(f"{BASE_URL}/api/phase4/live-config", headers=admin_headers, json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["max_notional_exposure"] == 150.0, "max_notional_exposure should be clamped to 150"

    def test_live_config_restricts_symbol_whitelist_to_btcusdt(self, admin_headers):
        """symbol_whitelist should be restricted to BTCUSDT in safe mode"""
        payload = {
            "exchange": "binance",
            "market_type": "futures_testnet",
            "safe_mode_enabled": True,
            "live_mode_enabled": False,
            "symbol_whitelist": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],  # Multiple symbols
            "max_position_pct": 0.1,
            "leverage_cap": 1,
            "max_trades_per_hour": 6,
            "max_notional_exposure": 150,
            "kill_switch_enabled": False,
            "disable_futures": False,
            "ip_whitelist_ready": False,
            "trading_permission_ready": False,
        }
        response = requests.put(f"{BASE_URL}/api/phase4/live-config", headers=admin_headers, json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["symbol_whitelist"] == ["BTCUSDT"], "symbol_whitelist should be restricted to BTCUSDT"

    def test_live_config_validation_rejects_invalid_leverage(self, admin_headers):
        """Leverage above schema max (3) should be rejected by validation"""
        payload = {
            "exchange": "binance",
            "market_type": "futures_testnet",
            "safe_mode_enabled": True,
            "live_mode_enabled": False,
            "symbol_whitelist": ["BTCUSDT"],
            "max_position_pct": 0.1,
            "leverage_cap": 10,  # Above schema max of 3
            "max_trades_per_hour": 6,
            "max_notional_exposure": 150,
            "kill_switch_enabled": False,
            "disable_futures": False,
            "ip_whitelist_ready": False,
            "trading_permission_ready": False,
        }
        response = requests.put(f"{BASE_URL}/api/phase4/live-config", headers=admin_headers, json=payload)
        assert response.status_code == 422, "Should reject leverage > 3"


class TestPhase4ReadinessCheck:
    """GET /api/phase4/readiness-check tests"""

    def test_readiness_check_returns_200(self, admin_headers):
        """Readiness check should return 200"""
        response = requests.get(f"{BASE_URL}/api/phase4/readiness-check", headers=admin_headers)
        assert response.status_code == 200

    def test_readiness_check_contains_testnet_connectivity_check(self, admin_headers):
        """Readiness check should contain testnet_endpoint_reachable check"""
        response = requests.get(f"{BASE_URL}/api/phase4/readiness-check", headers=admin_headers)
        data = response.json()
        
        assert "checks" in data
        check_keys = [check["key"] for check in data["checks"]]
        assert "testnet_endpoint_reachable" in check_keys

    def test_readiness_check_contains_safe_limits_check(self, admin_headers):
        """Readiness check should contain safe_limits_locked check"""
        response = requests.get(f"{BASE_URL}/api/phase4/readiness-check", headers=admin_headers)
        data = response.json()
        
        check_keys = [check["key"] for check in data["checks"]]
        assert "safe_limits_locked" in check_keys

    def test_readiness_check_response_structure(self, admin_headers):
        """Readiness check should have proper response structure"""
        response = requests.get(f"{BASE_URL}/api/phase4/readiness-check", headers=admin_headers)
        data = response.json()
        
        assert "mode" in data
        assert "exchange" in data
        assert "market_type" in data
        assert "checks" in data
        assert "safe_limits" in data
        assert "docs_references" in data
        
        # Validate safe_limits structure
        safe_limits = data["safe_limits"]
        assert "symbol_whitelist" in safe_limits
        assert "max_position_pct" in safe_limits
        assert "leverage_cap" in safe_limits
        assert "max_notional_exposure" in safe_limits

    def test_readiness_check_requires_admin(self):
        """Readiness check should require admin auth"""
        response = requests.get(f"{BASE_URL}/api/phase4/readiness-check")
        assert response.status_code == 401


class TestPhase4KillSwitch:
    """POST /api/phase4/kill-switch/* tests"""

    def test_kill_switch_stop_all_bots(self, admin_headers):
        """Kill switch stop-all-bots should return ok"""
        response = requests.post(f"{BASE_URL}/api/phase4/kill-switch/stop-all-bots", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["action"] == "stop_all_bots"

    def test_kill_switch_close_all_positions(self, admin_headers):
        """Kill switch close-all-positions should return ok"""
        response = requests.post(f"{BASE_URL}/api/phase4/kill-switch/close-all-positions", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["action"] == "close_all_positions"

    def test_kill_switch_disable_futures(self, admin_headers):
        """Kill switch disable-futures should return ok"""
        response = requests.post(f"{BASE_URL}/api/phase4/kill-switch/disable-futures", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["action"] == "disable_futures"

    def test_kill_switch_requires_admin(self):
        """Kill switch endpoints should require admin auth"""
        for endpoint in ["stop-all-bots", "close-all-positions", "disable-futures"]:
            response = requests.post(f"{BASE_URL}/api/phase4/kill-switch/{endpoint}")
            assert response.status_code == 401, f"{endpoint} should require auth"
