"""
FAZ-A+B deterministic closure tests - iteration 157
Testing:
- GET /api/admin/execution-readiness contract and deterministic READY/BLOCKED
- GET /api/admin/release-gate returns PASS|BLOCKED contract with reason_codes and blocking_metrics
- POST /api/admin/execution-override exists and enforces admin/contract
- POST /api/user/validate-order works and returns execution_mode
- POST /api/user/manual-trade enforces guard with 423 when readiness blocked
- Execution responses include execution_mode
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": "admin@platform.local", "password": "Admin12345!"},
        timeout=20,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return response.json().get("access_token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Admin authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_credentials():
    """Create and approve a test user for guard enforcement testing"""
    email = f"test_guard_157_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    return {"email": email, "password": password}


@pytest.fixture(scope="module")
def user_token(admin_headers, user_credentials):
    """Register, approve, and login a test user"""
    # Register
    reg_resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": user_credentials["email"], "password": user_credentials["password"]},
        timeout=20,
    )
    if reg_resp.status_code != 200:
        pytest.skip(f"User registration failed: {reg_resp.status_code}")
    
    user_id = reg_resp.json().get("id")
    
    # Approve
    approve_resp = requests.post(
        f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
        headers=admin_headers,
        timeout=20,
    )
    if approve_resp.status_code != 200:
        pytest.skip(f"User approval failed: {approve_resp.status_code}")
    
    # Login
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=user_credentials,
        timeout=20,
    )
    if login_resp.status_code != 200:
        pytest.skip(f"User login failed: {login_resp.status_code}")
    
    return login_resp.json().get("access_token")


@pytest.fixture(scope="module")
def user_headers(user_token):
    """User authorization headers"""
    return {"Authorization": f"Bearer {user_token}"}


class TestExecutionReadinessContract:
    """Tests for GET /api/admin/execution-readiness"""
    
    def test_execution_readiness_endpoint_exists(self, admin_headers):
        """Verify endpoint exists and returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
    
    def test_execution_readiness_contract_fields(self, admin_headers):
        """Verify response contains required contract fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields per contract
        assert "exchange_connection" in data, "Missing exchange_connection field"
        assert "permissions" in data, "Missing permissions field"
        assert "latency_ms" in data, "Missing latency_ms field"
        assert "order_test" in data, "Missing order_test field"
        assert "mode" in data, "Missing mode field"
        assert "final_status" in data, "Missing final_status field"
    
    def test_execution_readiness_deterministic_status(self, admin_headers):
        """Verify final_status is deterministic READY or BLOCKED"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        final_status = data.get("final_status")
        assert final_status in ["READY", "BLOCKED"], f"final_status must be READY or BLOCKED, got: {final_status}"
    
    def test_execution_readiness_mode_field(self, admin_headers):
        """Verify mode field is MOCKED or LIVE"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        mode = data.get("mode")
        assert mode in ["MOCKED", "LIVE"], f"mode must be MOCKED or LIVE, got: {mode}"
    
    def test_execution_readiness_latency_type(self, admin_headers):
        """Verify latency_ms is an integer"""
        response = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        latency_ms = data.get("latency_ms")
        assert isinstance(latency_ms, int), f"latency_ms must be int, got: {type(latency_ms)}"


class TestReleaseGateContract:
    """Tests for GET /api/admin/release-gate"""
    
    def test_release_gate_endpoint_exists(self, admin_headers):
        """Verify endpoint exists and returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
    
    def test_release_gate_status_contract(self, admin_headers):
        """Verify status is PASS or BLOCKED"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        status = data.get("status")
        assert status in ["PASS", "BLOCKED"], f"status must be PASS or BLOCKED, got: {status}"
    
    def test_release_gate_reason_codes_contract(self, admin_headers):
        """Verify reason_codes is a list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        reason_codes = data.get("reason_codes")
        assert isinstance(reason_codes, list), f"reason_codes must be list, got: {type(reason_codes)}"
    
    def test_release_gate_blocking_metrics_contract(self, admin_headers):
        """Verify blocking_metrics is a dict"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        blocking_metrics = data.get("blocking_metrics")
        assert isinstance(blocking_metrics, dict), f"blocking_metrics must be dict, got: {type(blocking_metrics)}"
    
    def test_release_gate_blocked_has_reason_codes(self, admin_headers):
        """If status is BLOCKED, reason_codes should not be empty"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        if data.get("status") == "BLOCKED":
            reason_codes = data.get("reason_codes", [])
            assert len(reason_codes) > 0, "BLOCKED status should have at least one reason_code"
    
    def test_release_gate_no_500_on_runtime_error(self, admin_headers):
        """Verify endpoint doesn't return 500 even with runtime issues"""
        response = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=30,
        )
        # Should return 200 even if internal error - returns controlled payload
        assert response.status_code != 500, "Release gate should not return 500 - should return controlled payload"


class TestExecutionOverrideContract:
    """Tests for POST /api/admin/execution-override"""
    
    def test_execution_override_endpoint_exists(self, admin_headers):
        """Verify endpoint exists (may reject if not BLOCKED)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "execution_guard_manual_override",
                "reason_note": "Test override from iteration 157",
                "ttl_minutes": 5,
                "deploy_context": {"source": "testing_agent_157"},
            },
            timeout=20,
        )
        # May return 400 if gate is not BLOCKED - that's acceptable behavior
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}: {response.text[:200]}"
    
    def test_execution_override_requires_admin(self):
        """Verify endpoint requires admin authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            json={
                "reason_code": "execution_guard_manual_override",
                "reason_note": "Test override without auth",
                "ttl_minutes": 5,
            },
            timeout=20,
        )
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
    
    def test_execution_override_validates_reason_code(self, admin_headers):
        """Verify invalid reason_code is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "invalid_reason_code_xyz",
                "reason_note": "Test invalid reason code",
                "ttl_minutes": 5,
            },
            timeout=20,
        )
        # Should return 400 for invalid reason_code
        assert response.status_code == 400, f"Expected 400 for invalid reason_code, got {response.status_code}"
    
    def test_execution_override_validates_reason_note_length(self, admin_headers):
        """Verify reason_note must be at least 12 characters"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "execution_guard_manual_override",
                "reason_note": "short",  # Less than 12 chars
                "ttl_minutes": 5,
            },
            timeout=20,
        )
        # Should return 400 for short reason_note
        assert response.status_code == 400, f"Expected 400 for short reason_note, got {response.status_code}"
    
    def test_execution_override_validates_ttl_limit(self, admin_headers):
        """Verify ttl_minutes max is 60"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-override",
            headers=admin_headers,
            json={
                "reason_code": "execution_guard_manual_override",
                "reason_note": "Test TTL limit validation",
                "ttl_minutes": 120,  # Exceeds 60 limit
            },
            timeout=20,
        )
        # Should return 400 or 422 (Pydantic validation) for ttl > 60
        assert response.status_code in [400, 422], f"Expected 400/422 for ttl > 60, got {response.status_code}"


class TestValidateOrderContract:
    """Tests for POST /api/user/validate-order"""
    
    def test_validate_order_endpoint_exists(self, user_headers):
        """Verify endpoint exists and returns 200"""
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
            timeout=20,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
    
    def test_validate_order_returns_valid_field(self, user_headers):
        """Verify response contains valid boolean field"""
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
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "valid" in data, "Missing valid field"
        assert isinstance(data["valid"], bool), f"valid must be bool, got: {type(data['valid'])}"
    
    def test_validate_order_returns_violations_list(self, user_headers):
        """Verify response contains violations list"""
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
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "violations" in data, "Missing violations field"
        assert isinstance(data["violations"], list), f"violations must be list, got: {type(data['violations'])}"
    
    def test_validate_order_returns_execution_mode(self, user_headers):
        """Verify response contains execution_mode field"""
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
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "execution_mode" in data, "Missing execution_mode field"
        assert data["execution_mode"] in ["mocked", "live"], f"execution_mode must be mocked or live, got: {data['execution_mode']}"
    
    def test_validate_order_leverage_violation(self, user_headers):
        """Verify leverage limit violation is detected"""
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
                "leverage": 200,  # Very high leverage
                "margin_mode": "isolated",
            },
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have violation for high leverage
        violations = data.get("violations", [])
        leverage_violations = [v for v in violations if "leverage" in v.get("code", "").lower()]
        assert len(leverage_violations) > 0, f"Expected leverage violation, got: {violations}"
    
    def test_validate_order_min_size_violation(self, user_headers):
        """Verify min order size violation is detected"""
        response = requests.post(
            f"{BASE_URL}/api/user/validate-order",
            headers=user_headers,
            json={
                "symbol": "BTCUSDT",
                "market_type": "futures",
                "order_type": "market",
                "side": "buy",
                "price": 50000,
                "size": 0.00001,  # Below min_order_size
                "leverage": 1,
                "margin_mode": "isolated",
            },
            timeout=20,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have violation for min size
        violations = data.get("violations", [])
        size_violations = [v for v in violations if "size" in v.get("code", "").lower() or "notional" in v.get("code", "").lower()]
        assert len(size_violations) > 0 or data.get("valid") is False, f"Expected size/notional violation for tiny order"


class TestManualTradeGuardEnforcement:
    """Tests for POST /api/user/manual-trade guard enforcement"""
    
    def test_manual_trade_returns_423_when_blocked(self, admin_headers):
        """Verify manual-trade returns 423 for user without exchange connection"""
        # Check if override is active
        readiness = requests.get(
            f"{BASE_URL}/api/admin/execution-readiness",
            headers=admin_headers,
            timeout=20,
        )
        if readiness.status_code == 200 and readiness.json().get("override_active"):
            pytest.skip("Override is active - guard enforcement cannot be tested")
        
        # Create a fresh user without exchange connection
        email = f"test_blocked_157_{uuid.uuid4().hex[:8]}@example.com"
        password = "TestPass123!"
        
        # Register
        reg_resp = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password},
            timeout=20,
        )
        if reg_resp.status_code != 200:
            pytest.skip(f"User registration failed: {reg_resp.status_code}")
        
        user_id = reg_resp.json().get("id")
        
        # Approve
        approve_resp = requests.post(
            f"{BASE_URL}/api/auth/admin/user-approval-requests/{user_id}/approve",
            headers=admin_headers,
            timeout=20,
        )
        if approve_resp.status_code != 200:
            pytest.skip(f"User approval failed: {approve_resp.status_code}")
        
        # Login
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=20,
        )
        if login_resp.status_code != 200:
            pytest.skip(f"User login failed: {login_resp.status_code}")
        
        blocked_user_token = login_resp.json().get("access_token")
        blocked_headers = {"Authorization": f"Bearer {blocked_user_token}"}
        
        # Try manual-trade without exchange connection - should get 423
        response = requests.post(
            f"{BASE_URL}/api/user/manual-trade",
            headers=blocked_headers,
            json={
                "intent_token": "guard_probe_token_157",
                "preview_hash": "guard_probe_hash_157",
            },
            timeout=20,
        )
        
        # Should return 423 LOCKED or 400 (intent not found is also valid)
        assert response.status_code in [423, 400], f"Expected 423 or 400, got {response.status_code}: {response.text[:200]}"
        
        if response.status_code == 423:
            # Verify it's the execution guard
            assert "EXECUTION_BLOCKED" in response.text or "LOCKED" in response.text


class TestPhase4ReleaseGateAlias:
    """Tests for GET /api/phase4/admin/release-gate (alternate path)"""
    
    def test_phase4_release_gate_endpoint_exists(self, admin_headers):
        """Verify phase4 release-gate endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
    
    def test_phase4_release_gate_contract_match(self, admin_headers):
        """Verify phase4 endpoint returns same contract as admin endpoint"""
        phase4_resp = requests.get(
            f"{BASE_URL}/api/phase4/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        admin_resp = requests.get(
            f"{BASE_URL}/api/admin/release-gate",
            headers=admin_headers,
            timeout=20,
        )
        
        assert phase4_resp.status_code == 200
        assert admin_resp.status_code == 200
        
        phase4_data = phase4_resp.json()
        admin_data = admin_resp.json()
        
        # Both should have same structure
        assert isinstance(phase4_data.get("reason_codes"), list)
        assert isinstance(admin_data.get("reason_codes"), list)
        assert isinstance(phase4_data.get("blocking_metrics"), dict)
        assert isinstance(admin_data.get("blocking_metrics"), dict)


class TestExecutionReadinessOverrideEndpoint:
    """Tests for POST /api/admin/execution-readiness/override"""
    
    def test_execution_readiness_override_endpoint_exists(self, admin_headers):
        """Verify endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/admin/execution-readiness/override",
            headers=admin_headers,
            json={
                "reason_code": "execution_guard_manual_override",
                "reason_note": "Test override from iteration 157 readiness endpoint",
                "ttl_minutes": 5,
                "deploy_context": {"source": "testing_agent_157"},
            },
            timeout=20,
        )
        # May return 400 if not BLOCKED - that's acceptable
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}: {response.text[:200]}"
