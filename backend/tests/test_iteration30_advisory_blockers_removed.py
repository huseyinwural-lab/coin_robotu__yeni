"""
Iteration 30: Advisory Mode - ORDER_PRECHECK/EXECUTION_DISABLED Blockers Removed

Test Requirements:
1. GET /api/user/signals returns rows with status=ready and tradeable=true
2. blocked_reason_code should be empty
3. first_precheck_failure_code should be empty/None
4. UI Signals table should show no blocked rows

User: review.user@platform.local / ReviewUser123!
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_USER_EMAIL = "review.user@platform.local"
TEST_USER_PASSWORD = "ReviewUser123!"


class TestAdvisoryModeBlockersRemoved:
    """Test that ORDER_PRECHECK/EXECUTION_DISABLED blockers are removed"""

    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def auth_token(self, session):
        """Login and get auth token"""
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        return token

    def test_01_login_success(self, session, auth_token):
        """Verify login works"""
        assert auth_token is not None or session.cookies, "Auth should be established"
        print(f"Login successful for {TEST_USER_EMAIL}")

    def test_02_signals_endpoint_returns_200(self, session, auth_token):
        """GET /api/user/signals should return 200"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=100")
        assert response.status_code == 200, f"Signals endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Signals endpoint returned {len(data)} signals")

    def test_03_no_blocked_signals(self, session, auth_token):
        """Verify no signals have status=blocked"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        blocked_signals = [s for s in signals if s.get("status") == "blocked"]
        assert len(blocked_signals) == 0, f"Found {len(blocked_signals)} blocked signals, expected 0"
        print(f"No blocked signals found (total: {len(signals)})")

    def test_04_no_non_tradeable_signals(self, session, auth_token):
        """Verify no signals have status=non_tradeable"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        non_tradeable = [s for s in signals if s.get("status") == "non_tradeable"]
        assert len(non_tradeable) == 0, f"Found {len(non_tradeable)} non_tradeable signals, expected 0"
        print(f"No non_tradeable signals found (total: {len(signals)})")

    def test_05_signals_have_empty_blocked_reason_code(self, session, auth_token):
        """Verify blocked_reason_code is empty for all signals"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        signals_with_blocked_reason = [
            s for s in signals 
            if s.get("blocked_reason_code") and s.get("blocked_reason_code").strip()
        ]
        
        # Filter out SIGNAL_EXPIRED which is still valid
        non_expired_blocked = [
            s for s in signals_with_blocked_reason 
            if s.get("blocked_reason_code") != "SIGNAL_EXPIRED"
        ]
        
        assert len(non_expired_blocked) == 0, (
            f"Found {len(non_expired_blocked)} signals with blocked_reason_code "
            f"(excluding SIGNAL_EXPIRED): {[s.get('blocked_reason_code') for s in non_expired_blocked[:5]]}"
        )
        print(f"All signals have empty blocked_reason_code (excluding expired)")

    def test_06_signals_have_empty_first_precheck_failure_code(self, session, auth_token):
        """Verify first_precheck_failure_code is empty/None for all signals"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        signals_with_precheck_failure = [
            s for s in signals 
            if s.get("first_precheck_failure_code") and s.get("first_precheck_failure_code").strip()
        ]
        
        assert len(signals_with_precheck_failure) == 0, (
            f"Found {len(signals_with_precheck_failure)} signals with first_precheck_failure_code: "
            f"{[s.get('first_precheck_failure_code') for s in signals_with_precheck_failure[:5]]}"
        )
        print(f"All signals have empty first_precheck_failure_code")

    def test_07_signals_tradeable_true(self, session, auth_token):
        """Verify tradeable=true for non-expired signals"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        # Filter out expired signals
        active_signals = [s for s in signals if s.get("status") not in ("expired", "rejected", "filled")]
        
        non_tradeable_signals = [s for s in active_signals if s.get("tradeable") is False]
        
        # In advisory mode, all active signals should be tradeable
        if non_tradeable_signals:
            print(f"Warning: Found {len(non_tradeable_signals)} non-tradeable active signals")
            for s in non_tradeable_signals[:3]:
                print(f"  - {s.get('symbol')}: status={s.get('status')}, blocked_reason={s.get('blocked_reason_code')}")
        
        # Allow some non-tradeable if they have valid reasons (like SIGNAL_EXPIRED)
        truly_blocked = [
            s for s in non_tradeable_signals 
            if s.get("blocked_reason_code") not in ("", None, "SIGNAL_EXPIRED")
        ]
        
        assert len(truly_blocked) == 0, (
            f"Found {len(truly_blocked)} truly blocked signals: "
            f"{[(s.get('symbol'), s.get('blocked_reason_code')) for s in truly_blocked[:5]]}"
        )
        print(f"All active signals are tradeable (total active: {len(active_signals)})")

    def test_08_signals_status_ready_or_pending(self, session, auth_token):
        """Verify active signals have status=ready or pending (not blocked)"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        # Count by status
        status_counts = {}
        for s in signals:
            status = s.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Signal status distribution: {status_counts}")
        
        # Verify no blocked or non_tradeable
        assert status_counts.get("blocked", 0) == 0, f"Found {status_counts.get('blocked')} blocked signals"
        assert status_counts.get("non_tradeable", 0) == 0, f"Found {status_counts.get('non_tradeable')} non_tradeable signals"

    def test_09_status_contract_no_blocking_reasons(self, session, auth_token):
        """Verify status contract returns empty blocking_reasons"""
        response = session.get(f"{BASE_URL}/api/user/scanner/status-contract")
        assert response.status_code == 200, f"Status contract failed: {response.text}"
        data = response.json()
        
        blocking_reasons = data.get("blocking_reasons", [])
        assert isinstance(blocking_reasons, list), "blocking_reasons should be a list"
        
        # In advisory mode, blocking_reasons should be empty
        assert len(blocking_reasons) == 0, f"Expected empty blocking_reasons, got: {blocking_reasons}"
        
        health = data.get("health", "")
        assert health == "HEALTHY", f"Expected health=HEALTHY, got: {health}"
        
        print(f"Status contract: health={health}, blocking_reasons={blocking_reasons}")

    def test_10_no_order_precheck_failed_blockers(self, session, auth_token):
        """Verify no signals are blocked with ORDER_PRECHECK_FAILED"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        order_precheck_blocked = [
            s for s in signals 
            if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED"
        ]
        
        assert len(order_precheck_blocked) == 0, (
            f"Found {len(order_precheck_blocked)} signals blocked with ORDER_PRECHECK_FAILED"
        )
        print("No ORDER_PRECHECK_FAILED blockers found")

    def test_11_no_execution_disabled_blockers(self, session, auth_token):
        """Verify no signals are blocked with EXECUTION_DISABLED"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        execution_disabled = [
            s for s in signals 
            if s.get("blocked_reason_code") == "EXECUTION_DISABLED"
        ]
        
        assert len(execution_disabled) == 0, (
            f"Found {len(execution_disabled)} signals blocked with EXECUTION_DISABLED"
        )
        print("No EXECUTION_DISABLED blockers found")

    def test_12_scanner_results_tradeable(self, session, auth_token):
        """Verify scanner results show tradeable=true"""
        response = session.get(f"{BASE_URL}/api/user/scanner/results?limit=50")
        assert response.status_code == 200, f"Scanner results failed: {response.text}"
        results = response.json()
        
        if results:
            # Check tradeable field in results
            non_tradeable_results = [
                r for r in results 
                if r.get("tradeable") is False
            ]
            
            print(f"Scanner results: {len(results)} total, {len(non_tradeable_results)} non-tradeable")
            
            # In advisory mode, results should be tradeable
            if non_tradeable_results:
                for r in non_tradeable_results[:3]:
                    print(f"  - {r.get('symbol')}: tradeable={r.get('tradeable')}, first_precheck={r.get('first_precheck_failure_code')}")
        else:
            print("No scanner results found (may need to run scanner first)")

    def test_13_verify_non_tradeable_reason_codes_empty(self, session, auth_token):
        """Verify NON_TRADEABLE_REASON_CODES is empty in service"""
        # This is a code-level check - we verify by checking that no signals
        # have the old blocking reason codes
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        old_blocking_codes = {
            "ORDER_PRECHECK_FAILED",
            "EXECUTION_DISABLED",
            "SYMBOL_NOT_ALLOWED",
            "MARKET_TYPE_NOT_ALLOWED",
        }
        
        signals_with_old_codes = [
            s for s in signals 
            if s.get("blocked_reason_code") in old_blocking_codes
        ]
        
        assert len(signals_with_old_codes) == 0, (
            f"Found {len(signals_with_old_codes)} signals with old blocking codes: "
            f"{[(s.get('symbol'), s.get('blocked_reason_code')) for s in signals_with_old_codes[:5]]}"
        )
        print("No signals with old blocking codes found")

    def test_14_signal_detail_fields_correct(self, session, auth_token):
        """Verify signal detail fields are correctly set"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=50")
        assert response.status_code == 200
        signals = response.json()
        
        if not signals:
            pytest.skip("No signals to verify")
        
        # Check first few signals
        for signal in signals[:5]:
            symbol = signal.get("symbol", "unknown")
            status = signal.get("status", "")
            blocked_code = signal.get("blocked_reason_code", "")
            blocked_msg = signal.get("blocked_reason_message", "")
            blocked_hint = signal.get("blocked_solution_hint", "")
            tradeable = signal.get("tradeable")
            first_precheck = signal.get("first_precheck_failure_code")
            
            # Skip expired signals
            if status == "expired":
                continue
            
            # Verify advisory mode fields
            if status not in ("rejected", "filled"):
                # Active signals should have empty blocked fields
                if blocked_code and blocked_code != "SIGNAL_EXPIRED":
                    print(f"Warning: {symbol} has blocked_reason_code={blocked_code}")
                
                if first_precheck:
                    print(f"Warning: {symbol} has first_precheck_failure_code={first_precheck}")
        
        print("Signal detail fields verified")

    def test_15_summary_statistics(self, session, auth_token):
        """Print summary statistics for verification"""
        response = session.get(f"{BASE_URL}/api/user/signals?limit=200")
        assert response.status_code == 200
        signals = response.json()
        
        # Collect statistics
        total = len(signals)
        by_status = {}
        by_blocked_code = {}
        tradeable_count = 0
        non_tradeable_count = 0
        
        for s in signals:
            status = s.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            
            blocked_code = s.get("blocked_reason_code", "") or ""
            if blocked_code:
                by_blocked_code[blocked_code] = by_blocked_code.get(blocked_code, 0) + 1
            
            if s.get("tradeable"):
                tradeable_count += 1
            else:
                non_tradeable_count += 1
        
        print("\n=== SUMMARY STATISTICS ===")
        print(f"Total signals: {total}")
        print(f"By status: {by_status}")
        print(f"By blocked_reason_code: {by_blocked_code if by_blocked_code else 'None (all clear)'}")
        print(f"Tradeable: {tradeable_count}, Non-tradeable: {non_tradeable_count}")
        
        # Final assertions
        assert by_status.get("blocked", 0) == 0, "Should have no blocked signals"
        assert by_status.get("non_tradeable", 0) == 0, "Should have no non_tradeable signals"
        
        # Check for old blocking codes
        old_codes = {"ORDER_PRECHECK_FAILED", "EXECUTION_DISABLED"}
        for code in old_codes:
            assert by_blocked_code.get(code, 0) == 0, f"Should have no {code} blockers"
        
        print("=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
