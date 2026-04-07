"""
Test Advisory Mode - Hard Block Removal (B+C Scope)
====================================================
Tests that:
1. /api/admin/system/remediate-config endpoint is removed/inactive
2. validate_execution_payload returns validation_status=valid (advisory-only)
3. validate_order_precheck returns valid=true (hard-block disabled)
4. Execution safety gate has empty hard_blockers and execution_authority=ALLOW
5. Scripts produce advisory-pass output
"""

import os
import pytest
import requests
import subprocess
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login/admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code}")
    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in login response")
    return token


class TestRemediateConfigEndpointRemoval:
    """Test that /api/admin/system/remediate-config endpoint is removed or inactive"""

    def test_remediate_config_get_not_found(self, admin_token):
        """GET /api/admin/system/remediate-config should return 404 or 405"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        # Should be 404 (not found) or 405 (method not allowed) since endpoint is removed
        assert resp.status_code in [404, 405, 422], f"Expected 404/405/422, got {resp.status_code}: {resp.text}"
        print(f"PASS: GET /api/admin/system/remediate-config returns {resp.status_code}")

    def test_remediate_config_post_not_found(self, admin_token):
        """POST /api/admin/system/remediate-config should return 404 or 405"""
        resp = requests.post(
            f"{BASE_URL}/api/admin/system/remediate-config",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "test"},
            timeout=30,
        )
        # Should be 404 (not found) or 405 (method not allowed) since endpoint is removed
        assert resp.status_code in [404, 405, 422], f"Expected 404/405/422, got {resp.status_code}: {resp.text}"
        print(f"PASS: POST /api/admin/system/remediate-config returns {resp.status_code}")


class TestExecutionPrecheckAdvisoryMode:
    """Test that execution precheck operates in advisory-only mode (no hard blocks)"""

    def test_validate_execution_payload_returns_valid_on_invalid_input(self, admin_token):
        """validate_execution_payload should return validation_status=valid even with invalid input"""
        # Send intentionally invalid payload
        invalid_payload = {
            "symbol": "",  # Empty symbol - would normally fail
            "market_type": "invalid_market",  # Invalid market type
            "side": "INVALID",  # Invalid side
            "order_type": "unknown",  # Unknown order type
            "leverage": 999,  # Excessive leverage
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/admin/execution-policies/validate-payload",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=invalid_payload,
            timeout=30,
        )
        
        # If endpoint doesn't exist, try alternative endpoint
        if resp.status_code == 404:
            resp = requests.post(
                f"{BASE_URL}/api/execution/validate-payload",
                headers={"Authorization": f"Bearer {admin_token}"},
                json=invalid_payload,
                timeout=30,
            )
        
        if resp.status_code == 404:
            # Try direct service test via execution precheck endpoint
            resp = requests.post(
                f"{BASE_URL}/api/execution/precheck",
                headers={"Authorization": f"Bearer {admin_token}"},
                json=invalid_payload,
                timeout=30,
            )
        
        if resp.status_code in [404, 405]:
            print("INFO: Execution payload validation endpoint not exposed via API - checking service directly")
            # The service is tested via unit test below
            pytest.skip("Endpoint not exposed - service tested via unit test")
        
        data = resp.json()
        # In advisory mode, validation_status should be "valid" with advisory_reject_reason_codes
        validation_status = data.get("validation_status", "")
        print(f"validation_status: {validation_status}")
        print(f"advisory_reject_reason_codes: {data.get('advisory_reject_reason_codes', [])}")
        assert validation_status == "valid", f"Expected validation_status=valid, got {validation_status}"
        print("PASS: validate_execution_payload returns validation_status=valid (advisory mode)")


class TestOrderPrecheckAdvisoryMode:
    """Test that order precheck operates in advisory-only mode"""

    def test_validate_order_precheck_returns_valid(self, admin_token):
        """validate_order_precheck should return valid=true (hard-block disabled)"""
        # Get user token for order precheck
        user_resp = requests.post(
            f"{BASE_URL}/api/auth/login/user",
            json={"email": "review.user@platform.local", "password": "ReviewUser123!"},
            timeout=30,
        )
        
        if user_resp.status_code != 200:
            # Use admin token if user login fails
            token = admin_token
        else:
            token = user_resp.json().get("access_token") or user_resp.json().get("token") or admin_token
        
        # Test order precheck with various inputs
        precheck_payload = {
            "symbol": "BTCUSDT",
            "market_type": "futures",
            "order_type": "market",
            "side": "BUY",
            "price": 50000.0,
            "size": 0.001,
            "leverage": 10,
            "margin_mode": "isolated",
        }
        
        resp = requests.post(
            f"{BASE_URL}/api/execution/order-precheck",
            headers={"Authorization": f"Bearer {token}"},
            json=precheck_payload,
            timeout=30,
        )
        
        if resp.status_code == 404:
            resp = requests.post(
                f"{BASE_URL}/api/user/execution/order-precheck",
                headers={"Authorization": f"Bearer {token}"},
                json=precheck_payload,
                timeout=30,
            )
        
        if resp.status_code in [404, 405]:
            print("INFO: Order precheck endpoint not exposed - checking service directly")
            pytest.skip("Endpoint not exposed - service tested via unit test")
        
        data = resp.json()
        valid = data.get("valid", False)
        microstructure_guard = data.get("microstructure_guard", {})
        
        print(f"valid: {valid}")
        print(f"microstructure_guard.state: {microstructure_guard.get('state')}")
        print(f"microstructure_guard.reason_codes: {microstructure_guard.get('reason_codes')}")
        
        assert valid is True, f"Expected valid=true, got {valid}"
        # Check that HARDBLOCK_DISABLED is in reason codes
        reason_codes = microstructure_guard.get("reason_codes", [])
        assert "HARDBLOCK_DISABLED" in reason_codes, f"Expected HARDBLOCK_DISABLED in reason_codes: {reason_codes}"
        print("PASS: validate_order_precheck returns valid=true with HARDBLOCK_DISABLED")


class TestExecutionSafetyGateAdvisoryMode:
    """Test that execution safety gate operates in advisory mode"""

    def test_execution_safety_gate_allows_execution(self, admin_token):
        """Execution safety gate should have empty hard_blockers and execution_authority=ALLOW"""
        resp = requests.get(
            f"{BASE_URL}/api/admin/execution-safety/gate",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=60,
        )
        
        if resp.status_code == 404:
            resp = requests.get(
                f"{BASE_URL}/api/execution-safety/gate",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=60,
            )
        
        if resp.status_code == 404:
            resp = requests.get(
                f"{BASE_URL}/api/admin/execution-readiness/safety-gate",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=60,
            )
        
        if resp.status_code in [404, 405]:
            print("INFO: Execution safety gate endpoint not found - checking alternative")
            # Try execution readiness endpoint
            resp = requests.get(
                f"{BASE_URL}/api/admin/execution-readiness",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=60,
            )
        
        if resp.status_code not in [200, 201]:
            pytest.skip(f"Execution safety gate endpoint not available: {resp.status_code}")
        
        data = resp.json()
        
        # Check hard_blockers is empty
        hard_blockers = data.get("hard_blockers", [])
        gate_state = data.get("gate_state", data.get("state", ""))
        execution_allowed = data.get("execution_allowed", True)
        
        print(f"gate_state: {gate_state}")
        print(f"hard_blockers: {hard_blockers}")
        print(f"execution_allowed: {execution_allowed}")
        
        # In advisory mode, hard_blockers should be empty
        assert hard_blockers == [], f"Expected empty hard_blockers, got {hard_blockers}"
        # Gate state should be READY
        assert gate_state in ["READY", "DEGRADED", ""], f"Expected READY/DEGRADED gate_state, got {gate_state}"
        # Execution should be allowed
        assert execution_allowed is True, f"Expected execution_allowed=true, got {execution_allowed}"
        print("PASS: Execution safety gate has empty hard_blockers and allows execution")


class TestScriptsAdvisoryPass:
    """Test that scripts produce advisory-pass output"""

    def test_final_release_gate_report_advisory_pass(self):
        """final_release_gate_report.sh should produce advisory-pass output"""
        script_path = Path("/app/scripts/final_release_gate_report.sh")
        if not script_path.exists():
            pytest.skip("Script not found")
        
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        print(f"returncode: {result.returncode}")
        
        # Script should exit with 0 (success)
        assert result.returncode == 0, f"Script failed with code {result.returncode}"
        # Output should contain advisory mode indicator
        assert "GO" in result.stdout or "advisory" in result.stdout.lower(), "Expected GO or advisory in output"
        print("PASS: final_release_gate_report.sh produces advisory-pass output")

    def test_prod_like_smoke_advisory_pass(self):
        """prod_like_smoke.sh should produce advisory-pass output"""
        script_path = Path("/app/scripts/prod_like_smoke.sh")
        if not script_path.exists():
            pytest.skip("Script not found")
        
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        print(f"returncode: {result.returncode}")
        
        assert result.returncode == 0, f"Script failed with code {result.returncode}"
        assert "PASS" in result.stdout or "advisory" in result.stdout.lower(), "Expected PASS or advisory in output"
        print("PASS: prod_like_smoke.sh produces advisory-pass output")

    def test_prod_kill_switch_dry_run_advisory_pass(self):
        """prod_kill_switch_dry_run.sh should produce advisory-pass output"""
        script_path = Path("/app/scripts/prod_kill_switch_dry_run.sh")
        if not script_path.exists():
            pytest.skip("Script not found")
        
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        print(f"returncode: {result.returncode}")
        
        assert result.returncode == 0, f"Script failed with code {result.returncode}"
        assert "PASS" in result.stdout or "advisory" in result.stdout.lower(), "Expected PASS or advisory in output"
        print("PASS: prod_kill_switch_dry_run.sh produces advisory-pass output")

    def test_prod_rollback_drill_advisory_pass(self):
        """prod_rollback_drill.sh should produce advisory-pass output"""
        script_path = Path("/app/scripts/prod_rollback_drill.sh")
        if not script_path.exists():
            pytest.skip("Script not found")
        
        result = subprocess.run(
            ["bash", str(script_path)],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        print(f"returncode: {result.returncode}")
        
        assert result.returncode == 0, f"Script failed with code {result.returncode}"
        assert "PASS" in result.stdout or "advisory" in result.stdout.lower(), "Expected PASS or advisory in output"
        print("PASS: prod_rollback_drill.sh produces advisory-pass output")


class TestServiceUnitTests:
    """Unit tests for service functions"""

    def test_validate_execution_payload_service(self):
        """Test validate_execution_payload service directly"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.execution_precheck_service import validate_execution_payload
        
        # Test with invalid payload
        invalid_payload = {
            "symbol": "",
            "market_type": "invalid",
            "side": "INVALID",
            "order_type": "unknown",
            "leverage": 999,
        }
        
        result = validate_execution_payload(invalid_payload)
        
        print(f"validation_status: {result.get('validation_status')}")
        print(f"reject_reason_codes: {result.get('reject_reason_codes')}")
        print(f"advisory_reject_reason_codes: {result.get('advisory_reject_reason_codes')}")
        
        # In advisory mode, validation_status should be "valid"
        assert result.get("validation_status") == "valid", f"Expected valid, got {result.get('validation_status')}"
        # reject_reason_codes should be empty (moved to advisory)
        assert result.get("reject_reason_codes") == [], f"Expected empty reject_reason_codes, got {result.get('reject_reason_codes')}"
        # advisory_reject_reason_codes should contain the issues
        assert len(result.get("advisory_reject_reason_codes", [])) > 0, "Expected advisory_reject_reason_codes to have issues"
        print("PASS: validate_execution_payload returns valid with advisory codes")

    def test_validate_order_precheck_service(self):
        """Test validate_order_precheck service directly"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        # Need to mock db session
        from unittest.mock import MagicMock
        
        from services.execution_readiness_service import validate_order_precheck
        
        mock_db = MagicMock()
        
        result = validate_order_precheck(
            mock_db,
            user_id="test-user",
            symbol="BTCUSDT",
            market_type="futures",
            order_type="market",
            side="BUY",
            price=50000.0,
            size=0.001,
            leverage=10,
            margin_mode="isolated",
        )
        
        print(f"valid: {result.get('valid')}")
        print(f"microstructure_guard: {result.get('microstructure_guard')}")
        print(f"checks: {result.get('checks')}")
        
        # Should return valid=true
        assert result.get("valid") is True, f"Expected valid=true, got {result.get('valid')}"
        # microstructure_guard should indicate HARDBLOCK_DISABLED
        guard = result.get("microstructure_guard", {})
        assert "HARDBLOCK_DISABLED" in guard.get("reason_codes", []), f"Expected HARDBLOCK_DISABLED in reason_codes"
        print("PASS: validate_order_precheck returns valid=true with HARDBLOCK_DISABLED")

    def test_futures_order_preflight_advisory_mode(self):
        """Test FuturesOrderPreflight operates in advisory mode"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from core.execution.futures_order_preflight import FuturesOrderPreflight
        from core.execution.futures_execution_contract import FuturesExecutionRequest
        
        preflight = FuturesOrderPreflight()
        
        # Create a request that would normally fail multiple checks
        request = FuturesExecutionRequest(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.001,
            leverage=100,  # High leverage
            reduce_only=False,
            order_type="MARKET",
        )
        
        # Context that would normally cause failures
        context = {
            "active_symbols": ["ETHUSDT"],  # BTCUSDT not in active symbols
            "max_trade_leverage": 5,  # Lower than requested
            "current_position_qty": 0,
            "margin_available": 0,  # No margin
            "margin_required": 1000,
            "live_mode_enabled": False,  # Live mode disabled
            "release_gate_status": "BLOCKED",  # Gate blocked
            "environment": "live",
            "go_live_validator": {"execution_allowed": False},
        }
        
        result = preflight.evaluate(request, context)
        
        print(f"preflight_pass: {result.get('preflight_pass')}")
        print(f"reason_code: {result.get('reason_code')}")
        print(f"checks: {result.get('checks')}")
        
        # In advisory mode, preflight should pass
        assert result.get("preflight_pass") is True, f"Expected preflight_pass=true, got {result.get('preflight_pass')}"
        assert result.get("reason_code") == "PASS", f"Expected reason_code=PASS, got {result.get('reason_code')}"
        
        # All checks should pass (with advisory_reason for failures)
        for check in result.get("checks", []):
            assert check.get("pass") is True, f"Check {check.get('key')} should pass in advisory mode"
            if check.get("advisory_reason"):
                print(f"  Advisory: {check.get('key')} - {check.get('advisory_reason')}")
        
        print("PASS: FuturesOrderPreflight operates in advisory mode")

    def test_execution_safety_gate_service(self):
        """Test execution safety gate service returns ALLOW"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from unittest.mock import MagicMock, patch
        
        # Mock the dependencies
        mock_db = MagicMock()
        
        with patch("services.execution_safety_core_service.evaluate_go_live_readiness") as mock_validator:
            with patch("services.execution_safety_core_service.run_bybit_live_order_smoke") as mock_smoke:
                mock_validator.return_value = {
                    "readiness_state": "READY",
                    "score": 90,
                    "execution_allowed": True,
                    "go_live_allowed": True,
                    "reason_codes": [],
                    "warnings": [],
                    "blocking_failures": [],
                    "execution_proof": {"real_metric_count": 1, "has_mocked_paths": False},
                }
                mock_smoke.return_value = {"status": "PASS", "reason_code": "BYBIT_ORDER_SMOKE_PASS"}
                
                from services.execution_safety_core_service import get_execution_safety_gate
                
                result = get_execution_safety_gate(mock_db, user_id=None, force_refresh=True)
                
                print(f"gate_state: {result.get('gate_state')}")
                print(f"execution_allowed: {result.get('execution_allowed')}")
                print(f"hard_blockers: {result.get('hard_blockers')}")
                
                # Gate should be READY
                assert result.get("gate_state") == "READY", f"Expected READY, got {result.get('gate_state')}"
                # Execution should be allowed
                assert result.get("execution_allowed") is True, f"Expected execution_allowed=true"
                # Hard blockers should be empty
                assert result.get("hard_blockers") == [], f"Expected empty hard_blockers, got {result.get('hard_blockers')}"
                
                print("PASS: Execution safety gate returns READY with empty hard_blockers")
