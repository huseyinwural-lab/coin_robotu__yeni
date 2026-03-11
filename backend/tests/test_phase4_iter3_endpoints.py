"""
Phase-4 Iteration-3 Endpoint Tests
Tests for:
  A) GET /api/exchange/validate: valid contract fields and error mapping
  B) POST /api/exchange/test-order: invalid credential handling (400 not 500)
  C) GET /api/market/ticker: bid/ask/mid_price/timestamp response
  D) Execution metrics persistence: order_id/exchange_order_id/price_avg/executed_qty/slippage_pct/execution_time_ms/status
  E) Permission drift trend endpoint: GET /api/phase4/admin/permission-drift-trend?days=7|30
  F) Release gate CI script validation
"""
import os
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL env var required"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_token_and_id():
    """Create/use test user and get token"""
    test_email = "TEST_phase4iter3@example.com"
    test_password = "TestPassword123!"
    
    # Try login first
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": test_email, "password": test_password},
    )
    
    if login_resp.status_code == 200:
        data = login_resp.json()
        return data["access_token"], data["user"]["id"]
    
    # If not found, register and approve the user
    admin_resp = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.dev", "password": "Admin12345!"},
    )
    admin_token = admin_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    # Register user
    reg_resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": test_email, "password": test_password},
    )
    if reg_resp.status_code not in [201, 200, 400]:
        pytest.skip(f"Could not create test user: {reg_resp.text}")
    
    # Get pending users and approve
    pending_resp = requests.get(
        f"{BASE_URL}/api/auth/admin/user-approval-requests?status=pending",
        headers=admin_headers,
    )
    if pending_resp.status_code == 200:
        for user in pending_resp.json():
            if user["email"] == test_email:
                requests.post(
                    f"{BASE_URL}/api/auth/admin/user-approval-requests/{user['id']}/approve",
                    headers=admin_headers,
                )
                break
    
    # Now login
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/user",
        json={"email": test_email, "password": test_password},
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Could not login test user: {login_resp.text}")
    
    data = login_resp.json()
    return data["access_token"], data["user"]["id"]


@pytest.fixture
def user_headers(user_token_and_id):
    token, _ = user_token_and_id
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ===============================================================================
# A) GET /api/exchange/validate - Contract fields and error mapping
# ===============================================================================
class TestExchangeValidateContract:
    """GET /api/exchange/validate contract validation"""

    def test_validate_endpoint_returns_expected_codes(self, user_headers):
        """GET exchange/validate should return 200 or 4xx with proper fields"""
        response = requests.get(f"{BASE_URL}/api/exchange/validate", headers=user_headers)
        # Can be 200 (success), 400 (missing key), or 403 (permission/ip issue)
        assert response.status_code in [200, 400, 403], \
            f"Expected 200/400/403, got {response.status_code}: {response.text}"

    def test_validate_success_response_has_all_fields(self, user_headers):
        """Successful validate should have required fields"""
        response = requests.get(f"{BASE_URL}/api/exchange/validate", headers=user_headers)
        
        # Get response data
        if response.status_code == 200:
            data = response.json()
        else:
            # Error response has detail object with same fields
            data = response.json().get("detail", {})
        
        # Required contract fields
        required_fields = ["exchange", "environment", "is_valid", "permissions", "can_trade", "can_withdraw", "reason_codes"]
        for field in required_fields:
            assert field in data, f"Validate response must have {field} field"

    def test_validate_missing_key_returns_400(self, user_headers):
        """Missing API key should return 400 with missing_credentials reason"""
        # First clear credentials
        clear_payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "",
            "api_secret": "",
        }
        requests.put(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers, json=clear_payload)
        
        response = requests.get(f"{BASE_URL}/api/exchange/validate", headers=user_headers)
        
        # Should be 400 for missing credentials
        assert response.status_code == 400, \
            f"Missing key should return 400, got {response.status_code}"
        
        detail = response.json().get("detail", {})
        if isinstance(detail, dict):
            reason_codes = detail.get("reason_codes", [])
            assert "missing_credentials" in reason_codes, \
                f"Missing key should have 'missing_credentials' reason, got: {reason_codes}"

    def test_validate_invalid_key_returns_400(self, user_headers):
        """Invalid API key should return 400"""
        # Set invalid credentials
        invalid_payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "INVALID_KEY_12345",
            "api_secret": "INVALID_SECRET_67890",
        }
        requests.put(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers, json=invalid_payload)
        
        response = requests.get(f"{BASE_URL}/api/exchange/validate", headers=user_headers)
        
        # Should be 400 for invalid key
        assert response.status_code == 400, \
            f"Invalid key should return 400, got {response.status_code}"

    def test_validate_reason_codes_mapping(self, user_headers):
        """Validate should return appropriate reason_codes"""
        response = requests.get(f"{BASE_URL}/api/exchange/validate", headers=user_headers)
        
        if response.status_code == 200:
            data = response.json()
        else:
            data = response.json().get("detail", {})
        
        reason_codes = data.get("reason_codes", [])
        assert isinstance(reason_codes, list), "reason_codes should be a list"
        
        # Valid reason codes that can be returned
        valid_reason_codes = [
            "missing_credentials", "invalid_key", "ip_restriction",
            "missing_trade_permission", "exchange_error_400", "exchange_error_401",
            "exchange_error_403", "exchange_unreachable"
        ]
        
        for code in reason_codes:
            # Some codes have dynamic suffix like exchange_error_XXX
            is_valid = any(
                code == valid or code.startswith("exchange_error_")
                for valid in valid_reason_codes
            )
            assert is_valid or code in valid_reason_codes, \
                f"Unknown reason code: {code}"


# ===============================================================================
# B) POST /api/exchange/test-order - Invalid credential handling
# ===============================================================================
class TestExchangeTestOrder:
    """POST /api/exchange/test-order invalid credential handling"""

    def test_test_order_invalid_credentials_returns_400(self, user_headers):
        """test-order with invalid credentials should return 400 not 500"""
        # Setup invalid credentials
        invalid_payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "FAKE_INVALID_KEY_123",
            "api_secret": "FAKE_INVALID_SECRET_456",
        }
        requests.put(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers, json=invalid_payload)
        
        response = requests.post(f"{BASE_URL}/api/exchange/test-order", headers=user_headers)
        
        # CRITICAL: Must NOT be 500
        assert response.status_code != 500, \
            f"test-order should NOT return 500 server error, got: {response.status_code}: {response.text}"
        
        # Should be 400
        assert response.status_code == 400, \
            f"test-order with invalid credentials should return 400, got: {response.status_code}"

    def test_test_order_graceful_block_no_key(self, user_headers):
        """test-order with no key should gracefully block"""
        # Clear credentials
        clear_payload = {
            "exchange": "binance",
            "mode": "testnet",
            "api_key": "",
            "api_secret": "",
        }
        requests.put(f"{BASE_URL}/api/phase4/exchange-settings", headers=user_headers, json=clear_payload)
        
        response = requests.post(f"{BASE_URL}/api/exchange/test-order", headers=user_headers)
        
        # Should be blocked gracefully with 400
        assert response.status_code == 400, \
            f"test-order with no key should return 400, got: {response.status_code}"
        
        # Should have meaningful error detail
        data = response.json()
        assert "detail" in data, "Error should have detail message"
        assert len(data["detail"]) > 5, "Error detail should be meaningful"


# ===============================================================================
# C) GET /api/market/ticker - Response validation
# ===============================================================================
class TestMarketTicker:
    """GET /api/market/ticker response validation"""

    def test_ticker_returns_200(self, user_headers):
        """GET market/ticker should return 200"""
        response = requests.get(f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT", headers=user_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_ticker_has_bid_ask_mid_price(self, user_headers):
        """Ticker should have bid/ask/mid_price fields"""
        response = requests.get(f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "bid" in data, "Ticker must have bid field"
        assert "ask" in data, "Ticker must have ask field"
        assert "mid_price" in data, "Ticker must have mid_price field"
        
        # Validate numeric types
        assert isinstance(data["bid"], (int, float)), "bid should be numeric"
        assert isinstance(data["ask"], (int, float)), "ask should be numeric"
        assert isinstance(data["mid_price"], (int, float)), "mid_price should be numeric"

    def test_ticker_has_timestamp(self, user_headers):
        """Ticker should have timestamp field"""
        response = requests.get(f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "timestamp" in data, "Ticker must have timestamp field"
        assert isinstance(data["timestamp"], str), "timestamp should be ISO string"

    def test_ticker_has_exchange_environment(self, user_headers):
        """Ticker should have exchange and environment fields"""
        response = requests.get(f"{BASE_URL}/api/market/ticker?symbol=BTCUSDT", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "exchange" in data, "Ticker must have exchange field"
        assert "environment" in data, "Ticker must have environment field"
        assert "symbol" in data, "Ticker must have symbol field"


# ===============================================================================
# D) Execution metrics persistence validation
# ===============================================================================
class TestExecutionMetricsPersistence:
    """Test execution_metrics table model/migration exists and response fields"""

    def test_execution_quality_endpoint_exists(self, admin_headers):
        """Admin execution quality endpoint should exist"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_execution_quality_items_have_required_fields(self, admin_headers):
        """Execution quality items should have required metric fields"""
        response = requests.get(f"{BASE_URL}/api/phase4/admin/execution-quality", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # If there are any items, validate their structure
        if len(data) > 0:
            item = data[0]
            
            # Required execution metric fields
            required_fields = [
                "execution_id",  # maps to order_id or id
                "symbol",
                "status",
                "strategy_type",
                "volatility_regime",
                "volatility_pct",
                "expected_price",  # maps to mid_price
                "execution_quality_score",
            ]
            
            for field in required_fields:
                assert field in item, f"Execution quality item must have {field} field"
            
            # Optional but important fields
            optional_fields = ["fill_price", "slippage", "execution_latency"]
            for field in optional_fields:
                assert field in item or f"{field}" in str(item), \
                    f"Execution quality should have {field} field"


# ===============================================================================
# E) Permission drift trend endpoint
# ===============================================================================
class TestPermissionDriftTrend:
    """GET /api/phase4/admin/permission-drift-trend validation"""

    def test_drift_trend_7_days(self, admin_headers):
        """permission-drift-trend?days=7 should return 200 with aggregation"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/permission-drift-trend?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["days"] == 7, f"Expected days=7, got {data['days']}"

    def test_drift_trend_30_days(self, admin_headers):
        """permission-drift-trend?days=30 should return 200 with aggregation"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/permission-drift-trend?days=30",
            headers=admin_headers,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["days"] == 30, f"Expected days=30, got {data['days']}"

    def test_drift_trend_has_points_array(self, admin_headers):
        """Drift trend should have points array for chart"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/permission-drift-trend?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "points" in data, "Must have points array"
        assert isinstance(data["points"], list), "points should be a list"
        
        # Points should have date/event_count/critical_count
        if len(data["points"]) > 0:
            point = data["points"][0]
            assert "date" in point, "Point must have date"
            assert "event_count" in point, "Point must have event_count"
            assert "critical_count" in point, "Point must have critical_count"

    def test_drift_trend_has_summary_fields(self, admin_headers):
        """Drift trend should have summary fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/permission-drift-trend?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Summary fields
        assert "affected_user_count" in data, "Must have affected_user_count"
        assert "critical_drift_count" in data, "Must have critical_drift_count"
        # latest_timestamp can be null if no events


# ===============================================================================
# F) Release gate CI script validation
# ===============================================================================
class TestReleaseGateCIScript:
    """Release gate CI script /app/scripts/run_release_gate_check.sh"""

    def test_script_file_exists(self):
        """Script file should exist at correct path"""
        import os
        script_path = "/app/scripts/run_release_gate_check.sh"
        assert os.path.exists(script_path), f"Script should exist at {script_path}"

    def test_script_is_executable(self):
        """Script should be executable"""
        import os
        script_path = "/app/scripts/run_release_gate_check.sh"
        assert os.access(script_path, os.X_OK), "Script should be executable"

    def test_script_outputs_release_gate_status(self):
        """Script should output release_gate_status line"""
        result = subprocess.run(
            ["bash", "/app/scripts/run_release_gate_check.sh"],
            capture_output=True,
            text=True,
            cwd="/app",
        )
        
        # Script may exit with 0 (PASS/WARNING) or 2 (BLOCKED)
        assert result.returncode in [0, 2], \
            f"Script should exit with 0 or 2, got {result.returncode}"
        
        # Output should contain release_gate_status
        output = result.stdout + result.stderr
        assert "release_gate_status=" in output, \
            f"Script should output release_gate_status, got: {output}"

    def test_script_blocked_returns_nonzero(self):
        """When BLOCKED, script should return non-zero exit code"""
        result = subprocess.run(
            ["bash", "/app/scripts/run_release_gate_check.sh"],
            capture_output=True,
            text=True,
            cwd="/app",
        )
        
        output = result.stdout + result.stderr
        
        # If output says BLOCKED, exit code should be 2
        if "release_gate_status=BLOCKED" in output:
            assert result.returncode == 2, \
                f"BLOCKED status should exit with code 2, got {result.returncode}"

    def test_script_can_parse_output(self):
        """Script output should be parseable for CI"""
        result = subprocess.run(
            ["bash", "/app/scripts/run_release_gate_check.sh"],
            capture_output=True,
            text=True,
            cwd="/app",
        )
        
        output = result.stdout
        lines = output.strip().split("\n")
        
        # Find the release_gate_status line
        status_line = None
        for line in lines:
            if line.startswith("release_gate_status="):
                status_line = line
                break
        
        assert status_line is not None, \
            f"Could not find release_gate_status line in output: {output}"
        
        # Parse the status value
        status = status_line.split("=")[1]
        assert status in ["PASS", "WARNING", "BLOCKED"], \
            f"release_gate_status should be PASS/WARNING/BLOCKED, got: {status}"


# ===============================================================================
# G) Monitoring endpoint release gate fields
# ===============================================================================
class TestMonitoringEndpointReleaseGate:
    """GET /api/pipeline/monitoring - release_gate_status and release_gate_last_checked"""

    def test_monitoring_has_release_gate_status(self, admin_headers):
        """Monitoring should have release_gate_status field"""
        response = requests.get(f"{BASE_URL}/api/pipeline/monitoring", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "release_gate_status" in data, "Monitoring must have release_gate_status"
        # Valid values
        assert data["release_gate_status"] in ["PASS", "WARNING", "BLOCKED", "UNKNOWN", "-"], \
            f"Invalid release_gate_status: {data['release_gate_status']}"

    def test_monitoring_has_release_gate_last_checked(self, admin_headers):
        """Monitoring should have release_gate_last_checked field"""
        response = requests.get(f"{BASE_URL}/api/pipeline/monitoring", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "release_gate_last_checked" in data, "Monitoring must have release_gate_last_checked"
        assert isinstance(data["release_gate_last_checked"], str), \
            "release_gate_last_checked should be a string"
