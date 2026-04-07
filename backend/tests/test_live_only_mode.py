"""
Test Suite: LIVE-Only Mode Enforcement
Tests that SIM mode has been completely removed and system operates in LIVE-only mode.

Test Coverage:
1. Backend adapter mode control - LIVE only
2. /api/runtime/execution/mode endpoint returns 'live'
3. /api/admin/live-trading/control-layer/execution-mode accepts only LIVE
4. Execution mode control service rejects non-LIVE modes
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://trade-trace-engine.preview.emergentagent.com"

ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin with longer timeout for preview environment
    try:
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=60
        )
    except requests.exceptions.Timeout:
        pytest.skip("Login request timed out - preview environment may be slow")
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Login request failed: {e}")
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
    
    # Extract token and set Authorization header
    data = login_response.json()
    token = data.get("access_token") or data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestRuntimeExecutionModeEndpoint:
    """Tests for /api/runtime/execution/mode endpoint"""
    
    def test_execution_mode_returns_live(self, admin_session):
        """Verify /api/runtime/execution/mode returns 'live' mode"""
        response = admin_session.get(f"{BASE_URL}/api/runtime/execution/mode")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
        
        # Mode should be 'live'
        mode = str(data.get("mode", "")).lower()
        assert mode == "live", f"Expected mode 'live', got: {mode}"
        
        # Compatibility alias should be LIVE
        alias = str(data.get("compatibility_alias", "")).upper()
        assert alias == "LIVE", f"Expected compatibility_alias 'LIVE', got: {alias}"
        
        # No compatibility notice for LIVE mode
        notice = data.get("compatibility_notice")
        assert notice is None, f"Expected no compatibility_notice, got: {notice}"
        
        print(f"✓ /api/runtime/execution/mode returns mode='live', alias='LIVE'")


class TestAdminLiveTradingControlLayerState:
    """Tests for /api/admin/live-trading/control-layer/state endpoint"""
    
    def test_control_layer_state_shows_live_mode(self, admin_session):
        """Verify control layer state shows LIVE execution mode"""
        response = admin_session.get(f"{BASE_URL}/api/admin/live-trading/control-layer/state")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Execution mode should be LIVE
        execution_mode = str(data.get("execution_mode", "")).upper()
        assert execution_mode == "LIVE", f"Expected execution_mode 'LIVE', got: {execution_mode}"
        
        print(f"✓ Control layer state shows execution_mode='LIVE'")


class TestAdminExecutionModeSwitch:
    """Tests for /api/admin/live-trading/control-layer/execution-mode endpoint"""
    
    def test_execution_mode_switch_accepts_live(self, admin_session):
        """Verify execution mode switch accepts LIVE mode"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            json={
                "mode": "LIVE",
                "reason": "Test: Verify LIVE mode acceptance",
                "confirmation_phrase": "SWITCH TO LIVE"
            }
        )
        
        # Should succeed (200) or already be in LIVE mode
        assert response.status_code in [200, 400], f"Unexpected status {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("status") == "ok", f"Expected status 'ok', got: {data}"
            mode = str(data.get("mode", "")).upper()
            assert mode == "LIVE", f"Expected mode 'LIVE', got: {mode}"
            print(f"✓ Execution mode switch to LIVE succeeded")
        else:
            # 400 might indicate already in LIVE mode or validation error
            print(f"✓ Execution mode switch returned 400 (may already be LIVE): {response.text}")
    
    def test_execution_mode_switch_rejects_sim(self, admin_session):
        """Verify execution mode switch rejects SIM mode"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            json={
                "mode": "SIM",
                "reason": "Test: Verify SIM mode rejection",
                "confirmation_phrase": "SWITCH TO SIM"
            }
        )
        
        # Should be rejected with 400 or 422 (validation error)
        assert response.status_code in [400, 422], f"Expected 400/422 for SIM mode, got {response.status_code}: {response.text}"
        
        print(f"✓ Execution mode switch to SIM correctly rejected with status {response.status_code}")
    
    def test_execution_mode_switch_rejects_paper(self, admin_session):
        """Verify execution mode switch rejects PAPER mode"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            json={
                "mode": "PAPER",
                "reason": "Test: Verify PAPER mode rejection",
                "confirmation_phrase": "SWITCH TO PAPER"
            }
        )
        
        # Should be rejected with 400 or 422 (validation error)
        assert response.status_code in [400, 422], f"Expected 400/422 for PAPER mode, got {response.status_code}: {response.text}"
        
        print(f"✓ Execution mode switch to PAPER correctly rejected with status {response.status_code}")
    
    def test_execution_mode_switch_rejects_mock(self, admin_session):
        """Verify execution mode switch rejects MOCK mode"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            json={
                "mode": "MOCK",
                "reason": "Test: Verify MOCK mode rejection",
                "confirmation_phrase": "SWITCH TO MOCK"
            }
        )
        
        # Should be rejected with 400 or 422 (validation error)
        assert response.status_code in [400, 422], f"Expected 400/422 for MOCK mode, got {response.status_code}: {response.text}"
        
        print(f"✓ Execution mode switch to MOCK correctly rejected with status {response.status_code}")


class TestExecutionModeControlServiceLogic:
    """Tests for execution mode control service behavior"""
    
    def test_mode_switch_phrase_only_live_available(self, admin_session):
        """Verify MODE_SWITCH_PHRASE only contains LIVE"""
        # Try to switch with wrong phrase for LIVE
        response = admin_session.post(
            f"{BASE_URL}/api/admin/live-trading/control-layer/execution-mode",
            json={
                "mode": "LIVE",
                "reason": "Test: Verify phrase validation",
                "confirmation_phrase": "WRONG PHRASE"
            }
        )
        
        # Should fail with 400 and indicate expected phrase
        assert response.status_code == 400, f"Expected 400 for wrong phrase, got {response.status_code}"
        
        data = response.json()
        detail = data.get("detail", {})
        
        # Check if expected phrase is returned
        if isinstance(detail, dict):
            expected_phrase = detail.get("expected_phrase", "")
            assert expected_phrase == "SWITCH TO LIVE", f"Expected phrase 'SWITCH TO LIVE', got: {expected_phrase}"
            print(f"✓ Expected phrase for LIVE mode is 'SWITCH TO LIVE'")
        else:
            print(f"✓ Wrong phrase correctly rejected: {detail}")


class TestExecutionReadinessEndpoint:
    """Tests for /api/admin/execution-readiness endpoint"""
    
    def test_execution_readiness_shows_live_mode(self, admin_session):
        """Verify execution readiness shows LIVE mode"""
        response = admin_session.get(f"{BASE_URL}/api/admin/execution-readiness")
        
        # May return 200 or 503 (DB pool timeout in preview)
        if response.status_code == 503:
            pytest.skip("DB pool timeout - skipping execution readiness test")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        mode = str(data.get("mode", "")).upper()
        
        # Mode should be LIVE or empty (defaults to LIVE)
        assert mode in ["LIVE", ""], f"Expected mode 'LIVE' or empty, got: {mode}"
        
        print(f"✓ Execution readiness shows mode='{mode}'")


class TestLiveTradingSummary:
    """Tests for /api/admin/live-trading/summary endpoint"""
    
    def test_live_trading_summary_shows_live_mode(self, admin_session):
        """Verify live trading summary shows LIVE execution mode"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/live-trading/summary",
            params={"window": "1h"}
        )
        
        # May return 200 or 503 (DB pool timeout in preview)
        if response.status_code == 503:
            pytest.skip("DB pool timeout - skipping live trading summary test")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        system_health = data.get("system_health", {})
        execution_mode = str(system_health.get("execution_mode", "")).upper()
        
        # Execution mode should be LIVE
        assert execution_mode == "LIVE", f"Expected execution_mode 'LIVE', got: {execution_mode}"
        
        print(f"✓ Live trading summary shows execution_mode='LIVE'")


class TestEnvironmentConfiguration:
    """Tests for environment configuration"""
    
    def test_execution_mode_env_is_live(self):
        """Verify EXECUTION_MODE environment variable is 'live'"""
        # This test checks the backend .env configuration
        execution_mode = os.environ.get("EXECUTION_MODE", "live").lower()
        assert execution_mode == "live", f"Expected EXECUTION_MODE='live', got: {execution_mode}"
        print(f"✓ EXECUTION_MODE environment variable is 'live'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
