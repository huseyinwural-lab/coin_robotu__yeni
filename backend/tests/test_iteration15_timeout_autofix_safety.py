"""
Iteration 15 - Timeout & Auto-Fix Safety Tests

Tests:
1. POST /api/user/signal/{id}/diagnose?auto_fix=true - response time <15s
2. POST /api/user/signals/fix-all-blockers?limit=10 - response time <15s
3. Auto-fix outputs should NOT contain unsafe actions (leverage/risk relax/lot increase/bypass)
4. Previous precheck/tradeable fields regression test
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_EMAIL = "review.user@platform.local"
TEST_PASSWORD = "ReviewUser123!"

# Unsafe action keywords that should NEVER appear in auto-fix outputs
UNSAFE_ACTION_KEYWORDS = [
    "leverage_increase",
    "leverage_relax",
    "risk_relax",
    "risk_increase",
    "lot_increase",
    "position_size_increase",
    "bypass",
    "skip_validation",
    "force_execute",
    "override_limit",
    "disable_guard",
]


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for test user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Auth failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestDiagnoseAutoFixTimeout:
    """Test diagnose endpoint with auto_fix=true response time"""

    def test_diagnose_auto_fix_response_time_under_15s(self, auth_headers):
        """POST /api/user/signal/{id}/diagnose?auto_fix=true should respond in <15s"""
        # First get a signal to diagnose
        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30,
        )
        assert signals_response.status_code == 200, f"Failed to get signals: {signals_response.text}"
        
        signals = signals_response.json()
        if not signals:
            pytest.skip("No signals available for testing")
        
        # Find a blocked or non_tradeable signal, or use any signal
        target_signal = None
        for signal in signals:
            status = str(signal.get("status", "")).lower()
            if status in {"blocked", "non_tradeable", "pending"}:
                target_signal = signal
                break
        
        if target_signal is None:
            target_signal = signals[0]  # Use first signal if no blocked ones
        
        signal_id = target_signal.get("id")
        assert signal_id, "Signal ID not found"
        
        # Measure response time for diagnose with auto_fix=true
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/user/signal/{signal_id}/diagnose",
            headers=auth_headers,
            params={"auto_fix": "true"},
            timeout=20,  # Set timeout slightly higher than expected
        )
        elapsed_time = time.time() - start_time
        
        print(f"Diagnose auto_fix=true response time: {elapsed_time:.2f}s")
        print(f"Response status: {response.status_code}")
        
        # Assert response time is under 15 seconds
        assert elapsed_time < 15, f"Diagnose auto_fix=true took {elapsed_time:.2f}s (expected <15s)"
        
        # Assert successful response
        assert response.status_code in {200, 404}, f"Unexpected status: {response.status_code} - {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"Diagnose response: status={data.get('status')}, actions_applied={data.get('actions_applied')}")
            
            # Verify no unsafe actions in response
            actions_applied = data.get("actions_applied", [])
            for action in actions_applied:
                action_lower = str(action).lower()
                for unsafe_keyword in UNSAFE_ACTION_KEYWORDS:
                    assert unsafe_keyword not in action_lower, f"Unsafe action detected: {action}"


class TestFixAllBlockersTimeout:
    """Test fix-all-blockers endpoint response time"""

    def test_fix_all_blockers_limit_10_response_time_under_15s(self, auth_headers):
        """POST /api/user/signals/fix-all-blockers?limit=10 should respond in <15s"""
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers",
            headers=auth_headers,
            params={"limit": 10},
            timeout=20,
        )
        elapsed_time = time.time() - start_time
        
        print(f"Fix-all-blockers limit=10 response time: {elapsed_time:.2f}s")
        print(f"Response status: {response.status_code}")
        
        # Assert response time is under 15 seconds
        assert elapsed_time < 15, f"Fix-all-blockers took {elapsed_time:.2f}s (expected <15s)"
        
        # Assert successful response
        assert response.status_code == 200, f"Unexpected status: {response.status_code} - {response.text}"
        
        data = response.json()
        print(f"Fix-all-blockers response: scanned={data.get('scanned_count')}, fixed={data.get('fixed_count')}")
        
        # Verify response structure
        assert "scanned_count" in data
        assert "fixed_count" in data
        assert "remaining_blocked" in data
        assert "actions_summary" in data
        
        # Verify no unsafe actions in actions_summary
        actions_summary = data.get("actions_summary", {})
        for action_key in actions_summary.keys():
            action_lower = str(action_key).lower()
            for unsafe_keyword in UNSAFE_ACTION_KEYWORDS:
                assert unsafe_keyword not in action_lower, f"Unsafe action in summary: {action_key}"


class TestAutoFixSafetyBoundaries:
    """Test that auto-fix actions are safe and don't include dangerous operations"""

    def test_diagnose_auto_fix_safe_actions_only(self, auth_headers):
        """Verify diagnose auto_fix only applies safe actions"""
        # Get signals
        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_headers,
            params={"limit": 100},
            timeout=30,
        )
        assert signals_response.status_code == 200
        
        signals = signals_response.json()
        
        # Test multiple signals if available
        tested_count = 0
        for signal in signals[:10]:  # Test up to 10 signals
            signal_id = signal.get("id")
            if not signal_id:
                continue
            
            response = requests.post(
                f"{BASE_URL}/api/user/signal/{signal_id}/diagnose",
                headers=auth_headers,
                params={"auto_fix": "true"},
                timeout=20,
            )
            
            if response.status_code == 200:
                data = response.json()
                actions_applied = data.get("actions_applied", [])
                
                # Check each action is safe
                safe_actions = {
                    "status_contract_refresh_requested",
                    "symbol_reload_requested",
                    "connection_revalidate_required",
                    "auto_dispatch_triggered",
                    "auto_dispatch_precheck_failed",
                }
                
                for action in actions_applied:
                    # Verify action is in safe list or doesn't contain unsafe keywords
                    is_safe = action in safe_actions
                    if not is_safe:
                        action_lower = str(action).lower()
                        for unsafe_keyword in UNSAFE_ACTION_KEYWORDS:
                            assert unsafe_keyword not in action_lower, f"Unsafe action: {action}"
                
                tested_count += 1
        
        print(f"Tested {tested_count} signals for safe auto-fix actions")
        assert tested_count > 0 or len(signals) == 0, "No signals tested"


class TestPrecheckTradeableRegression:
    """Regression tests for precheck and tradeable fields"""

    def test_signals_contain_tradeable_field(self, auth_headers):
        """Verify signals endpoint returns tradeable field"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30,
        )
        assert response.status_code == 200
        
        signals = response.json()
        if not signals:
            pytest.skip("No signals available")
        
        for signal in signals[:10]:
            assert "tradeable" in signal, f"Missing tradeable field in signal {signal.get('id')}"
            # tradeable should be boolean
            assert isinstance(signal["tradeable"], bool), f"tradeable should be boolean, got {type(signal['tradeable'])}"

    def test_signals_contain_first_precheck_failure_code(self, auth_headers):
        """Verify signals endpoint returns first_precheck_failure_code field"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30,
        )
        assert response.status_code == 200
        
        signals = response.json()
        if not signals:
            pytest.skip("No signals available")
        
        for signal in signals[:10]:
            # first_precheck_failure_code should exist (can be None or string)
            assert "first_precheck_failure_code" in signal, f"Missing first_precheck_failure_code in signal {signal.get('id')}"

    def test_scanner_results_contain_precheck_fields(self, auth_headers):
        """Verify scanner results contain tradeable and first_precheck_failure_code"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            headers=auth_headers,
            params={"limit": 50},
            timeout=30,
        )
        assert response.status_code == 200
        
        results = response.json()
        if not results:
            pytest.skip("No scanner results available")
        
        for result in results[:10]:
            # tradeable can be None or boolean
            assert "tradeable" in result, f"Missing tradeable field in result {result.get('id')}"
            assert "first_precheck_failure_code" in result, f"Missing first_precheck_failure_code in result {result.get('id')}"

    def test_exchange_readiness_endpoint(self, auth_headers):
        """Verify exchange-readiness endpoint returns required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/exchange-readiness",
            headers=auth_headers,
            params={"market_type": "spot"},
            timeout=30,
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Required fields
        assert "is_ready" in data
        assert "reason_code" in data
        assert "permissions" in data

    def test_status_contract_endpoint(self, auth_headers):
        """Verify status-contract endpoint returns blocking_reasons"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Required fields
        assert "scanner_ready" in data
        assert "strategy_ready" in data
        assert "risk_ready" in data
        assert "execution_ready" in data
        assert "blocking_reasons" in data
        assert isinstance(data["blocking_reasons"], list)


class TestBulkFixInternalLimit:
    """Test that bulk_fix_blocked_signals respects internal limit"""

    def test_fix_all_blockers_internal_limit_enforced(self, auth_headers):
        """Verify fix-all-blockers respects internal safe_limit (max 3)"""
        # Request with limit=10, but internal limit should cap at 3
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers",
            headers=auth_headers,
            params={"limit": 10},
            timeout=20,
        )
        assert response.status_code == 200
        
        data = response.json()
        scanned_count = data.get("scanned_count", 0)
        
        # Internal limit is max(min(limit, 3), 1) = 3
        # So scanned_count should be <= 3
        assert scanned_count <= 3, f"scanned_count={scanned_count} exceeds internal limit of 3"
        print(f"Fix-all-blockers scanned {scanned_count} signals (internal limit: 3)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
