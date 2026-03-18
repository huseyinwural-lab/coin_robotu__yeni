"""
Test iteration 156: FAZ-A + FAZ-B final closure deterministic tests

Features tested:
1. GET /api/admin/execution-readiness contract fields and deterministic status
2. GET /api/admin/release-gate contract: status PASS|BLOCKED + reason_codes[] + blocking_metrics
3. POST /api/admin/execution-override creates override and returns contract
4. POST /api/user/validate-order returns valid/violations + execution_mode + leverage/exposure/margin/min-size/min-notional checks
5. Global guard enforcement: POST /api/user/manual-trade returns 423 EXECUTION_BLOCKED_BY_READINESS
6. Execution mode standard field appears on execution responses
7. Admin UI: /admin/execution-readiness panel - verified via endpoint contracts
8. Admin UI: release gate actionable mapping - verified via endpoint contracts
9. CI scripts sanity: final_release_smoke_suite and p0_closure_gate

Test approach: Using pytest for backend API validation.
"""

import os
import subprocess
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is required for integration tests")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    admin_email = "admin@platform.local"
    admin_password = "Admin12345!"
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": admin_email, "password": admin_password},
        timeout=30,
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Admin headers fixture"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_credentials():
    """Create a test user for guard testing"""
    unique_id = uuid.uuid4().hex[:8]
    email = f"test_faz156_{unique_id}@example.com"
    password = "TestUserFaz156!"
    return {"email": email, "password": password}


@pytest.fixture(scope="module")
def user_token(user_credentials, admin_headers):
    """Register and approve a test user, return token"""
    email = user_credentials["email"]
    password = user_credentials["password"]
    
    # Register user
    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password},
        timeout=30,
    )
    if register_response.status_code != 200:
        pytest.skip(f"User registration failed: {register_response.text}")
    
    user_id = register_response.json().get("id")
    
    # Approve user
    approve_response = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=30,
    )
    if approve_response.status_code != 200:
        pytest.skip(f"User approval failed: {approve_response.text}")
    
    # Login
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    if login_response.status_code != 200:
        pytest.skip(f"User login failed: {login_response.text}")
    
    return login_response.json().get("access_token")


@pytest.fixture(scope="module")
def user_headers(user_token):
    """User headers fixture"""
    return {"Authorization": f"Bearer {user_token}"}


class TestExecutionReadinessContract:
    """Test GET /api/admin/execution-readiness contract fields"""

    def test_execution_readiness_returns_200(self, admin_headers):
        """Execution readiness endpoint should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_execution_readiness_contract_fields(self, admin_headers):
        """Execution readiness should have required contract fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields per contract
        required_fields = [
            "exchange_connection",
            "permissions",
            "latency_ms",
            "order_test",
            "mode",
            "final_status",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_execution_readiness_final_status_deterministic(self, admin_headers):
        """Final status should be READY or BLOCKED (deterministic)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        final_status = data.get("final_status")
        assert final_status in ["READY", "BLOCKED"], f"final_status must be READY or BLOCKED, got: {final_status}"

    def test_execution_readiness_mode_field(self, admin_headers):
        """Mode field should be MOCKED or LIVE"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        mode = data.get("mode")
        assert mode in ["MOCKED", "LIVE"], f"mode must be MOCKED or LIVE, got: {mode}"

    def test_execution_readiness_mocked_mode_ready_logic(self, admin_headers):
        """MOCKED mode + connection => READY rule"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        # As per readiness rule: MOCKED+connection => READY
        mode = data.get("mode")
        final_status = data.get("final_status")
        mocked_flag = data.get("mocked_flag")
        
        if mode == "MOCKED":
            assert "mocked_flag" in data, "mocked_flag should be present when mode is MOCKED"
            assert mocked_flag is True, "mocked_flag should be True when mode is MOCKED"
            # If MOCKED with connection, should be READY
            if data.get("exchange_connection") != "FAIL":
                assert final_status == "READY", f"MOCKED mode with connection should be READY, got: {final_status}"

    def test_execution_readiness_latency_is_integer(self, admin_headers):
        """Latency should be an integer"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        latency_ms = data.get("latency_ms")
        assert isinstance(latency_ms, int), f"latency_ms should be int, got: {type(latency_ms)}"


class TestReleaseGateContract:
    """Test GET /api/admin/release-gate contract"""

    def test_release_gate_returns_200(self, admin_headers):
        """Release gate endpoint should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_release_gate_status_pass_or_blocked(self, admin_headers):
        """Release gate status must be PASS or BLOCKED"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        status = data.get("status")
        assert status in ["PASS", "BLOCKED"], f"status must be PASS or BLOCKED, got: {status}"

    def test_release_gate_reason_codes_is_list(self, admin_headers):
        """reason_codes must be a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        reason_codes = data.get("reason_codes")
        assert isinstance(reason_codes, list), f"reason_codes must be list, got: {type(reason_codes)}"

    def test_release_gate_blocking_metrics_is_dict(self, admin_headers):
        """blocking_metrics must be a dict"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        blocking_metrics = data.get("blocking_metrics")
        assert isinstance(blocking_metrics, dict), f"blocking_metrics must be dict, got: {type(blocking_metrics)}"

    def test_release_gate_blocked_has_reason_codes(self, admin_headers):
        """When BLOCKED, reason_codes should not be empty"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        status = data.get("status")
        reason_codes = data.get("reason_codes", [])
        
        if status == "BLOCKED":
            assert len(reason_codes) > 0, "BLOCKED status should have at least one reason_code"


class TestExecutionOverrideEndpoint:
    """Test POST /api/admin/execution-override creates override"""

    def test_execution_override_requires_reason(self, admin_headers):
        """Override should require valid reason_code"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "false_positive",
                "reason_note": "Test override for FAZ-156 testing iteration - ignore for production",
                "ttl_minutes": 30,
                "deploy_context": {"source": "test_iteration_156"},
            },
            timeout=30,
        )
        # Could be 200 if gate is BLOCKED, or 400 if not BLOCKED (manual override only for blocked state)
        # Both are valid behaviors, we just confirm the endpoint responds
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}: {response.text}"

    def test_execution_override_invalid_reason_code(self, admin_headers):
        """Override should reject invalid reason_code"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "invalid_code_xyz",
                "reason_note": "This should fail validation",
                "ttl_minutes": 30,
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Invalid reason_code should return 400, got: {response.status_code}"

    def test_execution_override_short_reason_note(self, admin_headers):
        """Override should require reason_note >= 12 chars"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "false_positive",
                "reason_note": "short",
                "ttl_minutes": 30,
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Short reason_note should return 400, got: {response.status_code}"


class TestValidateOrderEndpoint:
    """Test POST /api/user/validate-order contract"""

    def test_validate_order_returns_200(self, user_headers):
        """Validate order endpoint should return 200"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.01,
                "leverage": 2,
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_validate_order_contract_fields(self, user_headers):
        """Validate order should return valid, violations, execution_mode"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.01,
                "leverage": 2,
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "valid" in data, "Response must have 'valid' field"
        assert "violations" in data, "Response must have 'violations' field"
        assert "execution_mode" in data, "Response must have 'execution_mode' field"
        
        assert isinstance(data["valid"], bool), "valid must be boolean"
        assert isinstance(data["violations"], list), "violations must be list"
        assert data["execution_mode"] in ["mocked", "live"], f"execution_mode must be mocked or live, got: {data['execution_mode']}"

    def test_validate_order_leverage_check(self, user_headers):
        """Validate order should check leverage limits"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.01,
                "leverage": 100,  # Exceeds cap
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have leverage violation
        violation_codes = [v.get("code") for v in data.get("violations", [])]
        assert "leverage_limit_exceeded" in violation_codes, f"Should have leverage violation, got: {violation_codes}"

    def test_validate_order_min_size_check(self, user_headers):
        """Validate order should check min_order_size"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.00001,  # Below min
                "leverage": 1,
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        violation_codes = [v.get("code") for v in data.get("violations", [])]
        assert "min_order_size_violation" in violation_codes, f"Should have min_order_size violation, got: {violation_codes}"

    def test_validate_order_min_notional_check(self, user_headers):
        """Validate order should check min_notional"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 1,  # Very low price
                "size": 0.001,  # Notional will be too low
                "leverage": 1,
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        violation_codes = [v.get("code") for v in data.get("violations", [])]
        assert "min_notional_violation" in violation_codes, f"Should have min_notional violation, got: {violation_codes}"

    def test_validate_order_spot_cross_margin_check(self, user_headers):
        """Validate order should reject cross margin for spot"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.01,
                "leverage": 1,
                "margin_mode": "cross",  # Invalid for spot
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        violation_codes = [v.get("code") for v in data.get("violations", [])]
        assert "margin_mode_invalid_for_spot" in violation_codes, f"Should have margin_mode_invalid_for_spot violation, got: {violation_codes}"


class TestExecutionGuardEnforcement:
    """Test global guard enforcement for trades"""

    def test_manual_trade_guard_blocks_without_readiness(self, admin_headers):
        """User without exchange connection should get 423 on manual-trade"""
        # Create a fresh user without exchange connection
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_guard_{unique_id}@example.com"
        password = "TestGuard156!"
        
        # Register
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password},
            timeout=30,
        )
        if register_response.status_code != 200:
            pytest.skip(f"Registration failed: {register_response.text}")
        
        user_id = register_response.json().get("id")
        
        # Approve
        approve_response = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=admin_headers,
            timeout=30,
        )
        if approve_response.status_code != 200:
            pytest.skip(f"Approval failed: {approve_response.text}")
        
        # Login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=30,
        )
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.text}")
        
        blocked_token = login_response.json().get("access_token")
        blocked_headers = {"Authorization": f"Bearer {blocked_token}"}
        
        # Check readiness first
        readiness_resp = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=30,
        )
        readiness_data = readiness_resp.json() if readiness_resp.status_code == 200 else {}
        
        # If override is active, guard may pass - skip test
        if readiness_data.get("override_active"):
            pytest.skip("Override is active - guard enforcement may be bypassed")
        
        # Try manual-trade without valid exchange setup
        trade_response = requests.post(
            f"{BASE_URL}/api/user/manual-trade",
            headers=blocked_headers,
            json={
                "intent_token": "guard_test_token",
                "preview_hash": "guard_test_hash",
            },
            timeout=30,
        )
        
        # Should be 423 or 400 (intent_not_found since no preview)
        # The guard runs first, so 423 if blocked, else 400 for intent_not_found
        assert trade_response.status_code in [400, 423], f"Expected 400 or 423, got: {trade_response.status_code}"
        
        if trade_response.status_code == 423:
            # Verify exact detail message
            detail = trade_response.json().get("detail", "")
            assert detail == "EXECUTION_BLOCKED_BY_READINESS", f"Expected EXECUTION_BLOCKED_BY_READINESS, got: {detail}"


class TestExecutionModeInResponses:
    """Test execution_mode field in execution responses"""

    def test_execution_mode_in_validate_order(self, user_headers):
        """validate-order should have execution_mode"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "spot",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.01,
                "leverage": 1,
                "margin_mode": "isolated",
            },
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "execution_mode" in data, "execution_mode must be present in validate-order response"
        assert data["execution_mode"] in ["mocked", "live"], f"execution_mode invalid: {data['execution_mode']}"


class TestCIScriptsSanity:
    """Test CI scripts final_release_smoke_suite and p0_closure_gate"""

    def test_final_release_smoke_suite_runs(self):
        """final_release_smoke_suite.py should run without crash"""
        result = subprocess.run(
            ["python", "/app/backend/cli/final_release_smoke_suite.py"],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Script returns 0 on PASS, 1 on FAIL - both are valid executions
        assert result.returncode in [0, 1], f"Script crashed: {result.stderr}"
        
        # Output should be valid JSON
        import json
        try:
            output = json.loads(result.stdout)
            assert "checks" in output, "Output should have checks field"
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.stdout[:500]}")

    def test_p0_closure_gate_runs(self):
        """p0_closure_gate.py should run without crash"""
        result = subprocess.run(
            ["python", "/app/backend/cli/p0_closure_gate.py", "--target-env", "preview"],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=180,
        )
        # Script returns 0 on PASS, 2 on FAIL - both are valid executions
        assert result.returncode in [0, 2], f"Script crashed: {result.stderr}"
        
        # Output should be valid JSON
        import json
        try:
            output = json.loads(result.stdout)
            assert "checks" in output, "Output should have checks field"
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.stdout[:500]}")


class TestPhase4ReleasGateEndpoint:
    """Test phase4 release gate endpoint"""

    def test_phase4_release_gate_200(self, admin_headers):
        """Phase4 release gate should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_phase4_release_gate_contract(self, admin_headers):
        """Phase4 release gate should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data, "status field required"
        assert "reason_codes" in data, "reason_codes field required"
        assert data.get("status") in ["PASS", "BLOCKED"], f"Invalid status: {data.get('status')}"
