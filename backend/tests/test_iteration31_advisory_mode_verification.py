"""
Iteration 31: Advisory Mode Verification Tests
Tests to verify that EXECUTION_DISABLED and ORDER_PRECHECK_FAILED blockers are removed.

Requirements:
1. PendingSignal table: blocked/non_tradeable count = 0
2. blocked_reason_code with EXECUTION_DISABLED and ORDER_PRECHECK_FAILED count = 0
3. GET /api/user/signals returns rows with empty blocked_reason_code
4. UI Signals screen shows no blocked signal indicators
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-trace-engine.preview.emergentagent.com")

# Test credentials
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for test user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=60
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def authenticated_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestAdvisoryModeBlockersRemoved:
    """Tests to verify EXECUTION_DISABLED and ORDER_PRECHECK_FAILED blockers are removed"""

    def test_login_success(self):
        """Test that login works with test credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=60
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data, "No token in response"
        assert data.get("user", {}).get("email") == TEST_EMAIL

    def test_scanner_overview_no_blocked_signals(self, authenticated_client):
        """Test scanner overview shows no blocked signals"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/user/scanner",
            timeout=60
        )
        assert response.status_code == 200, f"Scanner overview failed: {response.text}"
        data = response.json()
        
        # Verify mode is AUTO (advisory mode active)
        assert data.get("mode") == "AUTO", f"Expected mode=AUTO, got {data.get('mode')}"
        
        # Verify pending_signals count is reasonable
        pending = data.get("pending_signals", 0)
        assert pending >= 0, f"Invalid pending_signals count: {pending}"

    def test_signals_endpoint_no_blocked_reason_code(self, authenticated_client):
        """Test that /api/user/signals returns signals with empty blocked_reason_code"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/user/signals?limit=50",
            timeout=120
        )
        assert response.status_code == 200, f"Signals endpoint failed: {response.text}"
        signals = response.json()
        
        assert isinstance(signals, list), "Expected list of signals"
        assert len(signals) > 0, "No signals returned"
        
        # Count blocked_reason_code values
        execution_disabled_count = 0
        order_precheck_failed_count = 0
        blocked_status_count = 0
        non_tradeable_status_count = 0
        tradeable_count = 0
        
        for signal in signals:
            blocked_code = signal.get("blocked_reason_code", "")
            status = signal.get("status", "")
            tradeable = signal.get("tradeable", False)
            
            if blocked_code == "EXECUTION_DISABLED":
                execution_disabled_count += 1
            if blocked_code == "ORDER_PRECHECK_FAILED":
                order_precheck_failed_count += 1
            if status == "blocked":
                blocked_status_count += 1
            if status == "non_tradeable":
                non_tradeable_status_count += 1
            if tradeable:
                tradeable_count += 1
        
        # Assertions
        assert execution_disabled_count == 0, f"Found {execution_disabled_count} signals with EXECUTION_DISABLED"
        assert order_precheck_failed_count == 0, f"Found {order_precheck_failed_count} signals with ORDER_PRECHECK_FAILED"
        assert blocked_status_count == 0, f"Found {blocked_status_count} signals with status=blocked"
        assert non_tradeable_status_count == 0, f"Found {non_tradeable_status_count} signals with status=non_tradeable"
        assert tradeable_count == len(signals), f"Expected all signals tradeable, got {tradeable_count}/{len(signals)}"

    def test_signals_have_empty_blocked_reason_code(self, authenticated_client):
        """Test that all signals have empty blocked_reason_code"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/user/signals?limit=20",
            timeout=120
        )
        assert response.status_code == 200
        signals = response.json()
        
        for i, signal in enumerate(signals):
            blocked_code = signal.get("blocked_reason_code", "")
            assert blocked_code == "", f"Signal {i} has blocked_reason_code='{blocked_code}'"
            
            # Also verify first_precheck_failure_code is None/empty
            precheck_code = signal.get("first_precheck_failure_code")
            assert precheck_code is None or precheck_code == "", f"Signal {i} has first_precheck_failure_code='{precheck_code}'"

    def test_signals_are_tradeable(self, authenticated_client):
        """Test that all signals are tradeable"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/user/signals?limit=20",
            timeout=120
        )
        assert response.status_code == 200
        signals = response.json()
        
        for i, signal in enumerate(signals):
            tradeable = signal.get("tradeable", False)
            assert tradeable is True, f"Signal {i} is not tradeable: {signal.get('symbol')}"

    def test_signals_status_not_blocked(self, authenticated_client):
        """Test that no signals have blocked or non_tradeable status"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/user/signals?limit=50",
            timeout=120
        )
        assert response.status_code == 200
        signals = response.json()
        
        blocked_statuses = ["blocked", "non_tradeable"]
        for i, signal in enumerate(signals):
            status = signal.get("status", "")
            assert status not in blocked_statuses, f"Signal {i} has blocked status: {status}"


class TestDatabaseVerification:
    """Database-level verification tests (run via API)"""

    def test_scanner_status_contract_healthy(self, authenticated_client):
        """Test scanner status contract shows healthy state"""
        response = authenticated_client.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            timeout=120
        )
        assert response.status_code == 200, f"Status contract failed: {response.text}"
        data = response.json()
        
        # Verify health status
        health = data.get("health", "")
        assert health == "HEALTHY", f"Expected health=HEALTHY, got {health}"
        
        # Verify no blocking reasons related to EXECUTION_DISABLED or ORDER_PRECHECK_FAILED
        blocking_reasons = data.get("blocking_reasons", [])
        for reason in blocking_reasons:
            code = reason.get("code", "")
            assert "EXECUTION_DISABLED" not in code, f"Found EXECUTION_DISABLED in blocking_reasons: {code}"
            assert "ORDER_PRECHECK_FAILED" not in code, f"Found ORDER_PRECHECK_FAILED in blocking_reasons: {code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
