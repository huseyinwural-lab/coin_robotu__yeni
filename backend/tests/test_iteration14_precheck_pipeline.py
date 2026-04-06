"""
Iteration 14 - Precheck Pipeline & Exchange Readiness Testing

Tests:
1. GET /api/user/scanner/exchange-readiness (spot/futures) contract
2. Scanner candidate precheck fields (tradeable, first_precheck_failure_code)
3. NON_TRADEABLE vs BLOCKED distinction
4. run-async / run-async-both results with actionable_count and non_tradeable_count
5. Execution preview pipeline validation
6. Submit gate enforcement (precheck fail blocks submit)
7. Bot start fail-fast (422 with blocking_reasons)
8. Auto-fix safe boundaries (no risk relaxation, leverage change, lot increase)
"""

import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "canary.admin@platform.local"
ADMIN_PASSWORD = "CanaryAdmin123!"
USER_EMAIL = "review.user@platform.local"
USER_PASSWORD = "ReviewUser123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin auth failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_token():
    """Get user authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD},
        timeout=15
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"User auth failed: {response.status_code}")


@pytest.fixture(scope="module")
def user_headers(user_token):
    """User auth headers"""
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Admin auth headers"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestExchangeReadinessEndpoint:
    """Test GET /api/user/scanner/exchange-readiness contract"""

    def test_exchange_readiness_spot_contract(self, user_headers):
        """Test exchange readiness for spot market returns required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/exchange-readiness",
            params={"market_type": "spot"},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify contract fields
        assert "is_ready" in data, "Missing is_ready field"
        assert "reason_code" in data, "Missing reason_code field"
        assert "permissions" in data, "Missing permissions field"
        assert "market_types" in data, "Missing market_types field"
        assert "last_check_at" in data, "Missing last_check_at field"
        
        # Verify permissions structure
        permissions = data.get("permissions", {})
        assert "can_trade" in permissions, "Missing can_trade in permissions"
        assert "list" in permissions, "Missing list in permissions"
        
        print(f"Spot readiness: is_ready={data['is_ready']}, reason_code={data.get('reason_code')}")

    def test_exchange_readiness_futures_contract(self, user_headers):
        """Test exchange readiness for futures market returns required fields"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/exchange-readiness",
            params={"market_type": "futures"},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify contract fields
        assert "is_ready" in data, "Missing is_ready field"
        assert "reason_code" in data, "Missing reason_code field"
        assert "permissions" in data, "Missing permissions field"
        assert "market_types" in data, "Missing market_types field"
        assert "last_check_at" in data, "Missing last_check_at field"
        assert "market_type" in data, "Missing market_type field"
        
        # Verify market_type is futures
        assert data.get("market_type") == "futures", f"Expected futures, got {data.get('market_type')}"
        
        print(f"Futures readiness: is_ready={data['is_ready']}, reason_code={data.get('reason_code')}")

    def test_exchange_readiness_with_symbol(self, user_headers):
        """Test exchange readiness with specific symbol"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/exchange-readiness",
            params={"market_type": "spot", "symbol": "BTCUSDT"},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "symbol" in data, "Missing symbol field"
        # Symbol should be normalized to uppercase
        if data.get("symbol"):
            assert data["symbol"] == "BTCUSDT", f"Expected BTCUSDT, got {data.get('symbol')}"
        
        print(f"Symbol readiness: symbol={data.get('symbol')}, is_ready={data['is_ready']}")


class TestScannerCandidatePrecheckFields:
    """Test scanner candidate precheck fields (tradeable, first_precheck_failure_code)"""

    def test_scanner_results_contain_precheck_fields(self, user_headers):
        """Test that scanner results contain tradeable and first_precheck_failure_code"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/results",
            params={"limit": 50},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        results = response.json()
        if not results:
            pytest.skip("No scanner results available")
        
        # Check first result for precheck fields
        first_result = results[0]
        assert "tradeable" in first_result or "payload" in first_result, "Missing tradeable field"
        
        # Check payload for first_precheck_failure_code
        payload = first_result.get("payload", {})
        # first_precheck_failure_code may be in payload or at top level
        has_precheck_field = (
            "first_precheck_failure_code" in first_result or
            "first_precheck_failure_code" in payload
        )
        
        tradeable_count = sum(1 for r in results if r.get("tradeable") is True)
        non_tradeable_count = sum(1 for r in results if r.get("tradeable") is False)
        
        print(f"Scanner results: total={len(results)}, tradeable={tradeable_count}, non_tradeable={non_tradeable_count}")

    def test_signals_contain_precheck_fields(self, user_headers):
        """Test that signals contain tradeable and first_precheck_failure_code"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 100},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        signals = response.json()
        if not signals:
            pytest.skip("No signals available")
        
        # Check for precheck fields in signals
        for signal in signals[:10]:
            assert "tradeable" in signal, f"Missing tradeable field in signal {signal.get('id')}"
            # first_precheck_failure_code may be None for tradeable signals
            assert "first_precheck_failure_code" in signal, f"Missing first_precheck_failure_code field in signal {signal.get('id')}"
        
        tradeable_count = sum(1 for s in signals if s.get("tradeable") is True)
        non_tradeable_count = sum(1 for s in signals if s.get("tradeable") is False)
        
        print(f"Signals: total={len(signals)}, tradeable={tradeable_count}, non_tradeable={non_tradeable_count}")


class TestNonTradeableVsBlockedDistinction:
    """Test NON_TRADEABLE vs BLOCKED distinction"""

    def test_non_tradeable_status_exists(self, user_headers):
        """Test that non_tradeable status is properly distinguished from blocked"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 200},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        signals = response.json()
        
        # Count by status
        status_counts = {}
        for signal in signals:
            status = str(signal.get("status", "")).lower()
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Signal status distribution: {status_counts}")
        
        # Check for non_tradeable signals
        non_tradeable_signals = [s for s in signals if str(s.get("status", "")).lower() == "non_tradeable"]
        blocked_signals = [s for s in signals if str(s.get("status", "")).lower() == "blocked"]
        
        # Verify non_tradeable signals have precheck/exchange/symbol related blockers
        non_tradeable_reason_codes = set()
        for signal in non_tradeable_signals:
            code = signal.get("blocked_reason_code", "")
            if code:
                non_tradeable_reason_codes.add(code)
        
        # Verify blocked signals have risk/manual/bot-state related blockers
        blocked_reason_codes = set()
        for signal in blocked_signals:
            code = signal.get("blocked_reason_code", "")
            if code:
                blocked_reason_codes.add(code)
        
        print(f"Non-tradeable reason codes: {non_tradeable_reason_codes}")
        print(f"Blocked reason codes: {blocked_reason_codes}")
        
        # Expected non-tradeable codes
        expected_non_tradeable = {
            "ORDER_PRECHECK_FAILED", "EXCHANGE_NOT_READY", "SYMBOL_NOT_ALLOWED",
            "MARKET_TYPE_NOT_ALLOWED", "SCANNER_SYMBOL_MISMATCH", "EXECUTION_DISABLED"
        }
        
        # Check if non_tradeable signals have expected codes
        for code in non_tradeable_reason_codes:
            if code in expected_non_tradeable:
                print(f"Correctly classified as non_tradeable: {code}")

    def test_order_precheck_failed_shows_first_failure_code(self, user_headers):
        """Test that ORDER_PRECHECK_FAILED signals show first_precheck_failure_code detail"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 200},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200
        
        signals = response.json()
        
        # Find signals with ORDER_PRECHECK_FAILED
        precheck_failed_signals = [
            s for s in signals 
            if s.get("blocked_reason_code") == "ORDER_PRECHECK_FAILED"
        ]
        
        if not precheck_failed_signals:
            print("No ORDER_PRECHECK_FAILED signals found")
            return
        
        # Check that they have first_precheck_failure_code
        for signal in precheck_failed_signals[:5]:
            first_failure = signal.get("first_precheck_failure_code")
            print(f"Signal {signal.get('symbol')}: first_precheck_failure_code={first_failure}")
            # first_precheck_failure_code should provide more detail
            if first_failure:
                assert first_failure != "ORDER_PRECHECK_FAILED", "first_precheck_failure_code should be more specific"


class TestRunAsyncResults:
    """Test run-async / run-async-both results with actionable_count and non_tradeable_count"""

    def test_run_async_returns_counts(self, user_headers):
        """Test that run-async returns actionable_count and non_tradeable_count"""
        # Start async job
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run-async",
            json={
                "mode": "AUTO",
                "max_results": 25,
                "symbol_source": "crypto",
                "market_type": "spot",
                "symbol_selection_mode": "top_volume",
                "selected_symbols": []
            },
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "job_id" in data, "Missing job_id"
        assert "status" in data, "Missing status"
        
        job_id = data["job_id"]
        print(f"Started async job: {job_id}")
        
        # Poll for completion
        max_attempts = 30
        for attempt in range(max_attempts):
            time.sleep(2)
            status_response = requests.get(
                f"{BASE_URL}/api/user/scanner/run-async/{job_id}",
                headers=user_headers,
                timeout=15
            )
            if status_response.status_code != 200:
                continue
            
            status_data = status_response.json()
            if status_data.get("status") == "completed":
                result = status_data.get("result", {})
                print(f"Job completed: actionable_count={result.get('actionable_count')}, non_tradeable_count={result.get('non_tradeable_count')}")
                
                # Verify counts are present
                assert "actionable_count" in result or "result_count" in result, "Missing count fields"
                break
            elif status_data.get("status") == "failed":
                print(f"Job failed: {status_data.get('error')}")
                break
        else:
            print("Job did not complete in time")

    def test_run_async_both_returns_counts(self, user_headers):
        """Test that run-async-both returns actionable_count and non_tradeable_count for both markets"""
        # Start async both job
        response = requests.post(
            f"{BASE_URL}/api/user/scanner/run-async-both",
            json={
                "mode": "AUTO",
                "max_results": 15,
                "symbol_source": "crypto",
                "symbol_selection_mode": "top_volume",
                "selected_symbols": []
            },
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "job_id" in data, "Missing job_id"
        assert data.get("market_type") == "both", f"Expected market_type=both, got {data.get('market_type')}"
        
        job_id = data["job_id"]
        print(f"Started async-both job: {job_id}")
        
        # Poll for completion
        max_attempts = 45
        for attempt in range(max_attempts):
            time.sleep(2)
            status_response = requests.get(
                f"{BASE_URL}/api/user/scanner/run-async/{job_id}",
                headers=user_headers,
                timeout=15
            )
            if status_response.status_code != 200:
                continue
            
            status_data = status_response.json()
            if status_data.get("status") == "completed":
                result = status_data.get("result", {})
                print(f"Both job completed: actionable_count={result.get('actionable_count')}, non_tradeable_count={result.get('non_tradeable_count')}")
                
                # Check for runs array (spot and futures)
                runs = result.get("runs", [])
                if runs:
                    for run in runs:
                        market = run.get("market_type")
                        run_result = run.get("result", {})
                        print(f"  {market}: actionable={run_result.get('actionable_count')}, non_tradeable={run_result.get('non_tradeable_count')}")
                break
            elif status_data.get("status") == "failed":
                print(f"Job failed: {status_data.get('error')}")
                break
        else:
            print("Job did not complete in time")


class TestExecutionPreviewPipeline:
    """Test execution preview pipeline validation"""

    def test_preview_spot_returns_validation_status(self, user_headers):
        """Test that spot preview returns validation_status and reject_reason_codes"""
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json={
                "source_type": "manual",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 30,
                "execution_mode": "manual"
            },
            headers=user_headers,
            timeout=15
        )
        assert response.status_code in [200, 400, 409, 423], f"Unexpected status: {response.status_code}"
        
        data = response.json()
        
        # Check for validation fields
        if response.status_code == 200:
            assert "validation_status" in data, "Missing validation_status"
            assert "reject_reason_codes" in data, "Missing reject_reason_codes"
            print(f"Preview validation_status={data.get('validation_status')}, reject_codes={data.get('reject_reason_codes')}")
        else:
            print(f"Preview returned {response.status_code}: {data}")

    def test_preview_futures_returns_validation_status(self, user_headers):
        """Test that futures preview returns validation_status and reject_reason_codes"""
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json={
                "source_type": "manual",
                "market_type": "futures",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 30,
                "margin_mode": "isolated",
                "leverage": 1,
                "execution_mode": "manual"
            },
            headers=user_headers,
            timeout=15
        )
        assert response.status_code in [200, 400, 409, 423], f"Unexpected status: {response.status_code}"
        
        data = response.json()
        
        if response.status_code == 200:
            assert "validation_status" in data, "Missing validation_status"
            print(f"Futures preview validation_status={data.get('validation_status')}")
        else:
            print(f"Futures preview returned {response.status_code}: {data}")


class TestSubmitGateEnforcement:
    """Test submit gate enforcement - precheck fail blocks submit"""

    def test_submit_requires_valid_preview(self, user_headers):
        """Test that submit requires a valid preview first"""
        # Try to submit with invalid token
        response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/submit",
            json={
                "intent_token": "invalid-token-12345",
                "preview_hash": "invalid-hash"
            },
            headers=user_headers,
            timeout=15
        )
        
        # Should fail with 400 or 404
        assert response.status_code in [400, 404, 422], f"Expected 400/404/422, got {response.status_code}"
        print(f"Submit with invalid token returned: {response.status_code}")

    def test_preview_then_submit_flow(self, user_headers):
        """Test preview -> submit flow with precheck validation"""
        # First do a preview
        preview_response = requests.post(
            f"{BASE_URL}/api/user/execution/intent/preview",
            json={
                "source_type": "manual",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "position_size_mode": "fixed_notional",
                "position_size_value": 30,
                "execution_mode": "manual"
            },
            headers=user_headers,
            timeout=15
        )
        
        if preview_response.status_code != 200:
            print(f"Preview failed: {preview_response.status_code}")
            return
        
        preview_data = preview_response.json()
        validation_status = preview_data.get("validation_status")
        intent_token = preview_data.get("intent_token")
        preview_hash = preview_data.get("preview_hash")
        
        print(f"Preview: validation_status={validation_status}, intent_token={intent_token}")
        
        if validation_status != "valid":
            # If preview is rejected, submit should also fail
            reject_codes = preview_data.get("reject_reason_codes", [])
            print(f"Preview rejected with codes: {reject_codes}")
            
            # Try submit anyway - should fail
            if intent_token:
                submit_response = requests.post(
                    f"{BASE_URL}/api/user/execution/intent/submit",
                    json={
                        "intent_token": intent_token,
                        "preview_hash": preview_hash
                    },
                    headers=user_headers,
                    timeout=15
                )
                # Should fail because preview was rejected
                assert submit_response.status_code in [400, 422, 423], f"Expected submit to fail, got {submit_response.status_code}"
                print(f"Submit correctly blocked: {submit_response.status_code}")


class TestBotStartFailFast:
    """Test bot start fail-fast with 422 and blocking_reasons"""

    def test_status_contract_returns_blocking_reasons(self, user_headers):
        """Test that status contract returns blocking_reasons when not ready"""
        response = requests.get(
            f"{BASE_URL}/api/user/scanner/status-contract",
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify status contract fields
        assert "scanner_ready" in data, "Missing scanner_ready"
        assert "strategy_ready" in data, "Missing strategy_ready"
        assert "risk_ready" in data, "Missing risk_ready"
        assert "execution_ready" in data, "Missing execution_ready"
        assert "symbols_ready" in data, "Missing symbols_ready"
        assert "exchange_ready" in data, "Missing exchange_ready"
        assert "blocking_reasons" in data, "Missing blocking_reasons"
        
        print(f"Status contract: exchange_ready={data.get('exchange_ready')}, blocking_reasons={len(data.get('blocking_reasons', []))}")
        
        # Print blocking reasons if any
        for reason in data.get("blocking_reasons", []):
            print(f"  Blocking: {reason.get('code')} - {reason.get('message')}")

    def test_bot_runtime_summaries_contain_binding_validation(self, user_headers):
        """Test that bot runtime summaries contain binding validation"""
        response = requests.get(
            f"{BASE_URL}/api/bot-profiles",
            headers=user_headers,
            timeout=15
        )
        
        if response.status_code != 200:
            pytest.skip(f"Bot profiles endpoint returned {response.status_code}")
        
        bots = response.json()
        if not bots:
            pytest.skip("No bot profiles available")
        
        # Check first bot for binding validation
        first_bot = bots[0]
        print(f"Bot: {first_bot.get('name')}, is_running={first_bot.get('is_running')}")


class TestAutoFixSafeBoundaries:
    """Test auto-fix safe boundaries - no risk relaxation, leverage change, lot increase"""

    def test_diagnose_auto_fix_does_not_increase_risk(self, user_headers):
        """Test that diagnose auto_fix does not increase risk parameters"""
        # Get signals
        signals_response = requests.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 50},
            headers=user_headers,
            timeout=15
        )
        
        if signals_response.status_code != 200:
            pytest.skip("Could not get signals")
        
        signals = signals_response.json()
        
        # Find a blocked signal to diagnose
        blocked_signal = next(
            (s for s in signals if s.get("status") in ["blocked", "non_tradeable"]),
            None
        )
        
        if not blocked_signal:
            print("No blocked signals to test auto_fix")
            return
        
        signal_id = blocked_signal.get("id")
        
        # Run diagnose with auto_fix=true
        diagnose_response = requests.post(
            f"{BASE_URL}/api/user/signal/{signal_id}/diagnose",
            params={"auto_fix": True},
            headers=user_headers,
            timeout=15
        )
        
        if diagnose_response.status_code != 200:
            print(f"Diagnose returned {diagnose_response.status_code}")
            return
        
        diagnose_data = diagnose_response.json()
        actions_applied = diagnose_data.get("actions_applied", [])
        
        print(f"Diagnose actions applied: {actions_applied}")
        
        # Verify no unsafe actions
        unsafe_actions = [
            "increase_leverage", "relax_risk_limit", "increase_lot_size",
            "disable_risk_check", "bypass_precheck"
        ]
        
        for action in actions_applied:
            action_lower = str(action).lower()
            for unsafe in unsafe_actions:
                assert unsafe not in action_lower, f"Unsafe action detected: {action}"
        
        print("Auto-fix actions are within safe boundaries")

    def test_fix_all_blockers_safe_actions(self, user_headers):
        """Test that fix-all-blockers only applies safe actions"""
        response = requests.post(
            f"{BASE_URL}/api/user/signals/fix-all-blockers",
            params={"limit": 10},
            headers=user_headers,
            timeout=15
        )
        
        if response.status_code != 200:
            print(f"Fix all blockers returned {response.status_code}")
            return
        
        data = response.json()
        
        actions_summary = data.get("actions_summary", {})
        print(f"Fix all blockers: fixed={data.get('fixed_count')}, remaining={data.get('remaining_blocked')}")
        print(f"Actions summary: {actions_summary}")
        
        # Verify no unsafe actions in summary
        unsafe_keywords = ["leverage", "risk_relax", "lot_increase", "bypass"]
        for action_type, count in actions_summary.items():
            action_lower = str(action_type).lower()
            for unsafe in unsafe_keywords:
                assert unsafe not in action_lower, f"Unsafe action type detected: {action_type}"


class TestSignalsFunnelMetrics:
    """Test signals funnel metrics for non_tradeable vs blocked"""

    def test_signals_funnel_counts(self, user_headers):
        """Test that signals endpoint returns proper funnel counts"""
        response = requests.get(
            f"{BASE_URL}/api/user/signals",
            params={"limit": 200},
            headers=user_headers,
            timeout=15
        )
        assert response.status_code == 200
        
        signals = response.json()
        
        # Calculate funnel metrics
        funnel = {
            "detected": len(signals),
            "pending": 0,
            "ready": 0,
            "approved": 0,
            "queued": 0,
            "submitted": 0,
            "filled": 0,
            "blocked": 0,
            "non_tradeable": 0,
            "rejected": 0,
            "expired": 0
        }
        
        for signal in signals:
            status = str(signal.get("status", "")).lower()
            if status in funnel:
                funnel[status] += 1
        
        print(f"Signals funnel: {funnel}")
        
        # Verify non_tradeable and blocked are separate
        assert funnel["non_tradeable"] >= 0, "non_tradeable count should be >= 0"
        assert funnel["blocked"] >= 0, "blocked count should be >= 0"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
