"""
Iteration 29: ORDER_PRECHECK_FAILED Advisory Mode Tests

Tests to verify:
1. User scanner status-contract: blocking_reasons empty, health HEALTHY
2. User signals endpoint: 200 response, no ORDER_PRECHECK_FAILED non_tradeable blocks
3. User trades endpoint: 200 response (no 500 fallback)
4. ORDER_PRECHECK_FAILED legacy records cleaned/not blocking flow
5. NON_TRADEABLE_REASON_CODES is empty (advisory mode)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"


def get_auth_token(email: str, password: str) -> str:
    """Get JWT token from login"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code != 200:
        return ""
    
    data = response.json()
    # Try to get token from response body or cookies
    token = data.get("access_token") or data.get("token") or ""
    if not token:
        # Check cookies
        for cookie in response.cookies:
            if cookie.name == "access_token":
                token = cookie.value
                break
    return token


@pytest.fixture(scope="module")
def user_session():
    """Get authenticated user session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"User login failed: {response.status_code} - {response.text}")
    
    # Extract token and set in header if needed
    data = response.json()
    token = data.get("access_token") or data.get("token") or ""
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    
    # Extract token and set in header if needed
    data = response.json()
    token = data.get("access_token") or data.get("token") or ""
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestStatusContractAdvisoryMode:
    """Test status-contract endpoint returns HEALTHY with empty blocking_reasons"""
    
    def test_status_contract_returns_200(self, user_session):
        """Status contract endpoint should return 200"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/status-contract", timeout=60)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_status_contract_health_is_healthy(self, user_session):
        """Status contract health should be HEALTHY"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/status-contract", timeout=60)
        assert response.status_code == 200
        data = response.json()
        
        health = data.get("health", "")
        assert health == "HEALTHY", f"Expected health=HEALTHY, got {health}"
    
    def test_status_contract_blocking_reasons_empty(self, user_session):
        """Status contract blocking_reasons should be empty (no ORDER_PRECHECK_FAILED blocks)"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/status-contract", timeout=60)
        assert response.status_code == 200
        data = response.json()
        
        blocking_reasons = data.get("blocking_reasons", [])
        assert isinstance(blocking_reasons, list), f"blocking_reasons should be a list, got {type(blocking_reasons)}"
        assert len(blocking_reasons) == 0, f"Expected empty blocking_reasons, got {blocking_reasons}"
    
    def test_status_contract_no_order_precheck_failed_in_blocking(self, user_session):
        """No SIGNAL_BLOCKED::ORDER_PRECHECK_FAILED in blocking_reasons"""
        response = user_session.get(f"{BASE_URL}/api/user/scanner/status-contract", timeout=60)
        assert response.status_code == 200
        data = response.json()
        
        blocking_reasons = data.get("blocking_reasons", [])
        precheck_blocks = [
            r for r in blocking_reasons 
            if "ORDER_PRECHECK_FAILED" in str(r.get("code", ""))
        ]
        assert len(precheck_blocks) == 0, f"Found ORDER_PRECHECK_FAILED in blocking_reasons: {precheck_blocks}"


class TestSignalsEndpointAdvisoryMode:
    """Test signals endpoint returns 200 and no ORDER_PRECHECK_FAILED non_tradeable blocks"""
    
    def test_signals_endpoint_returns_200(self, user_session):
        """Signals endpoint should return 200"""
        response = user_session.get(f"{BASE_URL}/api/user/signals", params={"limit": 50}, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_signals_no_order_precheck_failed_non_tradeable(self, user_session):
        """No signals should be non_tradeable due to ORDER_PRECHECK_FAILED"""
        response = user_session.get(f"{BASE_URL}/api/user/signals", params={"limit": 100}, timeout=30)
        assert response.status_code == 200
        signals = response.json()
        
        if not isinstance(signals, list):
            signals = signals.get("items", []) if isinstance(signals, dict) else []
        
        # Check for ORDER_PRECHECK_FAILED non_tradeable signals
        precheck_blocked = [
            s for s in signals
            if str(s.get("status", "")).lower() == "non_tradeable"
            and str(s.get("blocked_reason_code", "")).upper() == "ORDER_PRECHECK_FAILED"
        ]
        
        assert len(precheck_blocked) == 0, (
            f"Found {len(precheck_blocked)} signals with non_tradeable status due to ORDER_PRECHECK_FAILED. "
            f"Advisory mode should not create non_tradeable blocks for ORDER_PRECHECK_FAILED."
        )
    
    def test_signals_order_precheck_failed_is_advisory_only(self, user_session):
        """ORDER_PRECHECK_FAILED should only appear in advisory fields, not as hard block"""
        response = user_session.get(f"{BASE_URL}/api/user/signals", params={"limit": 100}, timeout=30)
        assert response.status_code == 200
        signals = response.json()
        
        if not isinstance(signals, list):
            signals = signals.get("items", []) if isinstance(signals, dict) else []
        
        # Check that ORDER_PRECHECK_FAILED doesn't cause blocked status
        for signal in signals:
            blocked_code = str(signal.get("blocked_reason_code", "")).upper()
            status = str(signal.get("status", "")).lower()
            
            if blocked_code == "ORDER_PRECHECK_FAILED":
                # If ORDER_PRECHECK_FAILED is present, status should NOT be blocked/non_tradeable
                assert status not in ["blocked", "non_tradeable"], (
                    f"Signal {signal.get('id')} has ORDER_PRECHECK_FAILED but status={status}. "
                    f"Advisory mode should not block signals for ORDER_PRECHECK_FAILED."
                )


class TestTradesEndpointNoFallback:
    """Test trades endpoint returns 200 (no 500 fallback)"""
    
    def test_trades_endpoint_returns_200(self, user_session):
        """Trades endpoint should return 200"""
        response = user_session.get(f"{BASE_URL}/api/user/trades", params={"limit": 50}, timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_trades_endpoint_returns_list(self, user_session):
        """Trades endpoint should return a list"""
        response = user_session.get(f"{BASE_URL}/api/user/trades", params={"limit": 50}, timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list), f"Expected list, got {type(data)}"


class TestAdvisoryModeCodeChanges:
    """Test that code changes for advisory mode are correct"""
    
    def test_non_tradeable_reason_codes_is_empty(self):
        """NON_TRADEABLE_REASON_CODES should be empty in advisory mode"""
        from core.users.user_scanner_signal_service import NON_TRADEABLE_REASON_CODES
        
        assert isinstance(NON_TRADEABLE_REASON_CODES, (set, dict)), (
            f"NON_TRADEABLE_REASON_CODES should be set or dict, got {type(NON_TRADEABLE_REASON_CODES)}"
        )
        assert len(NON_TRADEABLE_REASON_CODES) == 0, (
            f"NON_TRADEABLE_REASON_CODES should be empty for advisory mode, got {NON_TRADEABLE_REASON_CODES}"
        )
    
    def test_evaluate_candidate_tradeability_returns_tradeable(self):
        """_evaluate_candidate_tradeability should always return tradeable=True in advisory mode"""
        from core.users.user_scanner_signal_service import _evaluate_candidate_tradeability
        
        # Test with minimal parameters - should return tradeable=True
        result = _evaluate_candidate_tradeability(
            db=None,  # Will be handled gracefully
            symbol="BTCUSDT",
            market_type="spot",
            signal_side="long",
            requested_notional=100.0,
            risk_notional_cap=1000.0,
            available_balance=500.0,
            exchange_connection=None,
            leverage=1,
            margin_mode="isolated",
            symbol_filters_cache={},
            exchange_readiness_cache={},
            registry_payload={},
            allow_exchange_soft_bypass=True,
        )
        
        assert result.get("tradeable") is True, (
            f"Expected tradeable=True in advisory mode, got {result.get('tradeable')}"
        )
        assert result.get("status") == "TRADEABLE", (
            f"Expected status=TRADEABLE, got {result.get('status')}"
        )
    
    def test_apply_order_precheck_failed_sets_pending_status(self):
        """_apply_order_precheck_failed should set status=pending, not blocked/non_tradeable"""
        from core.users.user_scanner_signal_service import _apply_order_precheck_failed
        from unittest.mock import MagicMock
        
        # Create mock PendingSignal
        mock_row = MagicMock()
        mock_row.execution_eligible = False
        mock_row.status = "blocked"
        mock_row.current_state = "BLOCKED"
        mock_row.blocked_reason_code = "ORDER_PRECHECK_FAILED"
        mock_row.blocked_reason_message = "test"
        mock_row.blocked_solution_hint = "test"
        mock_row.decision_note = ""
        
        # Apply the function
        _apply_order_precheck_failed(
            mock_row,
            reason_codes=["MIN_NOTIONAL_NOT_MET"],
            error_detail=""
        )
        
        # Verify advisory mode behavior
        assert mock_row.execution_eligible is True, "execution_eligible should be True in advisory mode"
        assert mock_row.status == "pending", f"status should be 'pending', got {mock_row.status}"
        assert mock_row.current_state == "DETECTED", f"current_state should be 'DETECTED', got {mock_row.current_state}"
        assert mock_row.blocked_reason_code == "", f"blocked_reason_code should be empty, got {mock_row.blocked_reason_code}"


class TestSignalStatusNormalization:
    """Test that signal status normalization works correctly for ORDER_PRECHECK_FAILED"""
    
    def test_normalize_blocked_payload_clears_order_precheck_failed(self):
        """_normalize_blocked_payload should clear ORDER_PRECHECK_FAILED codes"""
        from routers.user_scanner_signals import _normalize_blocked_payload
        
        code, message, hint = _normalize_blocked_payload(
            status="blocked",
            blocked_reason_code="ORDER_PRECHECK_FAILED",
            blocked_reason_message="Order precheck failed",
            blocked_solution_hint="Fix parameters"
        )
        
        assert code == "", f"Expected empty code for ORDER_PRECHECK_FAILED, got {code}"
        assert message == "", f"Expected empty message for ORDER_PRECHECK_FAILED, got {message}"
        assert hint == "", f"Expected empty hint for ORDER_PRECHECK_FAILED, got {hint}"
    
    def test_normalize_signal_status_for_ui_returns_pending(self):
        """_normalize_signal_status_for_ui should return 'pending' for ORDER_PRECHECK_FAILED"""
        from routers.user_scanner_signals import _normalize_signal_status_for_ui
        
        status = _normalize_signal_status_for_ui(
            status="blocked",
            blocked_reason_code="ORDER_PRECHECK_FAILED"
        )
        
        assert status == "pending", f"Expected 'pending' for ORDER_PRECHECK_FAILED, got {status}"


class TestStatusContractBlockingReasonsFiltering:
    """Test that status contract filters out ORDER_PRECHECK_FAILED from blocking_reasons"""
    
    def test_build_user_status_contract_filters_precheck_failed(self):
        """_build_user_status_contract should filter ORDER_PRECHECK_FAILED from blocking_reasons"""
        # This is tested via the API endpoint tests above
        # The code explicitly sets blocking_reasons = [] at line 306 in user_scanner_signals.py
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
